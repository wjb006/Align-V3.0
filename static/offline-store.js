// Align offline-first browser storage.
// Keeps a local cache of successful API reads and an outbox of shift batches
// created while the Python/SQLite server cannot be reached.
const AlignOffline = (() => {
  const DB_NAME = 'align-offline-v1';
  const DB_VERSION = 1;
  const CACHE_STORE = 'api_cache';
  const OUTBOX_STORE = 'outbox';

  function openDb() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(CACHE_STORE)) db.createObjectStore(CACHE_STORE, { keyPath: 'key' });
        if (!db.objectStoreNames.contains(OUTBOX_STORE)) db.createObjectStore(OUTBOX_STORE, { keyPath: 'requestId' });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('Unable to open offline storage.'));
    });
  }

  async function withStore(name, mode, action) {
    const db = await openDb();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(name, mode);
        const store = tx.objectStore(name);
        let result;
        try { result = action(store); } catch (error) { reject(error); return; }
        tx.oncomplete = () => resolve(result?.result);
        tx.onerror = () => reject(tx.error || new Error('Offline storage failed.'));
        tx.onabort = () => reject(tx.error || new Error('Offline storage was cancelled.'));
      });
    } finally { db.close(); }
  }

  async function putCache(key, payload) {
    await withStore(CACHE_STORE, 'readwrite', store => store.put({ key, payload, savedAt: Date.now() }));
  }

  async function getCache(key) {
    const db = await openDb();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(CACHE_STORE, 'readonly');
        const request = tx.objectStore(CACHE_STORE).get(key);
        request.onsuccess = () => resolve(request.result?.payload ?? null);
        request.onerror = () => reject(request.error || new Error('Unable to read offline cache.'));
      });
    } finally { db.close(); }
  }

  async function queueShiftBatch(body) {
    if (!body?.request_id || !Array.isArray(body.shifts) || !body.shifts.length) {
      throw new Error('This shift batch cannot be stored offline safely.');
    }
    await withStore(OUTBOX_STORE, 'readwrite', store => store.put({
      requestId: body.request_id,
      kind: 'shift-batch',
      path: '/api/shifts',
      method: 'POST',
      body,
      createdAt: Date.now(),
    }));
  }

  async function queueOrganiserEvent(path, body) {
    if (!body?.request_id || !/^\/api\/sections\/\d+\/events$/.test(path)) {
      throw new Error('This event cannot be stored offline safely.');
    }
    await withStore(OUTBOX_STORE, 'readwrite', store => store.put({
      requestId: body.request_id,
      kind: 'organiser-event',
      path,
      method: 'POST',
      body,
      createdAt: Date.now(),
    }));
  }

  async function listOutbox() {
    const db = await openDb();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(OUTBOX_STORE, 'readonly');
        const request = tx.objectStore(OUTBOX_STORE).getAll();
        request.onsuccess = () => resolve((request.result || []).sort((a, b) => a.createdAt - b.createdAt));
        request.onerror = () => reject(request.error || new Error('Unable to read offline changes.'));
      });
    } finally { db.close(); }
  }

  async function removeOutbox(requestId) {
    await withStore(OUTBOX_STORE, 'readwrite', store => store.delete(requestId));
  }

  function minutes(time) {
    const [hour, minute] = String(time || '00:00').split(':').map(Number);
    return hour * 60 + minute;
  }

  function shiftHours(start, end, breakMinutes = 0) {
    let finish = minutes(end), begin = minutes(start);
    if (finish <= begin) finish += 1440;
    return Math.max(0, Math.round(((finish - begin - Number(breakMinutes || 0)) / 60) * 100) / 100);
  }

  function stableNegativeId(requestId, index) {
    let hash = 2166136261;
    const text = `${requestId}:${index}`;
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return -Math.max(1, Math.abs(hash | 0));
  }

  async function pendingShifts(master) {
    if (!master?.templates) return [];
    const outbox = await listOutbox();
    const shifts = [];
    for (const item of outbox.filter(entry => entry.kind === 'shift-batch')) {
      item.body.shifts.forEach((draft, index) => {
        const template = master.templates.find(t => Number(t.id) === Number(draft.template_id));
        if (!template) return;
        const shiftType = master.shift_types?.find(t => Number(t.id) === Number(template.shift_type_id));
        const start = draft.start_time || template.start_time;
        const end = draft.end_time || template.end_time;
        const breakMinutes = draft.break_minutes ?? template.break_minutes ?? 0;
        shifts.push({
          id: stableNegativeId(item.requestId, index),
          work_date: draft.work_date || draft.date,
          template_id: Number(template.id),
          location_id: Number(template.location_id),
          shift_type_id: Number(template.shift_type_id),
          location_name: template.location_name,
          shift_type_name: template.shift_type_name,
          colour: template.colour,
          location_colour: template.colour,
          shift_type_colour: shiftType?.colour || '#3B82F6',
          start_time: start,
          end_time: end,
          break_minutes: Number(breakMinutes),
          hours: shiftHours(start, end, breakMinutes),
          notes: String(draft.notes || ''),
          pending_sync: true,
          offline_request_id: item.requestId,
        });
      });
    }
    return shifts;
  }

  async function pendingOrganiserEvents(sectionId) {
    const outbox = await listOutbox();
    return outbox.filter(item => item.kind === 'organiser-event' && item.path === `/api/sections/${sectionId}/events`).map((item, index) => ({
      id: stableNegativeId(item.requestId, index),
      section_id: Number(sectionId),
      title: String(item.body.title || 'Event'),
      start_at: item.body.all_day ? `${item.body.date}T00:00` : item.body.start_at,
      end_at: item.body.all_day ? `${addDays(item.body.date, 1)}T00:00` : item.body.end_at,
      all_day: item.body.all_day ? 1 : 0,
      location: String(item.body.location || ''),
      notes: String(item.body.notes || ''),
      source_kind: 'align',
      pending_sync: true,
      offline_request_id: item.requestId,
    }));
  }

  function uniqueShifts(shifts) {
    const seen = new Set();
    return shifts.filter(shift => {
      const key = shift.pending_sync
        ? `pending:${shift.offline_request_id}:${shift.work_date}:${shift.template_id}:${shift.start_time}`
        : `server:${shift.id}`;
      if (seen.has(key)) return false;
      seen.add(key); return true;
    }).sort((a, b) => `${a.work_date} ${a.start_time}`.localeCompare(`${b.work_date} ${b.start_time}`));
  }

  function inRange(shift, start, end) { return (!start || shift.work_date >= start) && (!end || shift.work_date <= end); }

  function mondayForIso(iso) {
    const value = new Date(`${iso}T12:00:00`);
    const day = value.getDay() || 7;
    value.setDate(value.getDate() - day + 1);
    const y = value.getFullYear(), m = String(value.getMonth() + 1).padStart(2, '0'), d = String(value.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  function addDays(iso, count) {
    const value = new Date(`${iso}T12:00:00`); value.setDate(value.getDate() + count);
    const y = value.getFullYear(), m = String(value.getMonth() + 1).padStart(2, '0'), d = String(value.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  async function overlay(path, payload) {
    if (!payload || typeof payload !== 'object') return payload;
    const master = path === '/api/bootstrap' ? payload.master : (window.ALIGN_STATE?.boot?.master || null);
    const pending = await pendingShifts(master);
    if (!pending.length) return payload;
    const copy = typeof structuredClone === 'function' ? structuredClone(payload) : JSON.parse(JSON.stringify(payload));

    if (path === '/api/bootstrap') {
      const today = copy.dashboard?.today;
      const weekStart = copy.dashboard?.week_start || (today ? mondayForIso(today) : null);
      const weekEnd = weekStart ? addDays(weekStart, 6) : null;
      if (copy.dashboard) {
        copy.dashboard.upcoming = uniqueShifts([...(copy.dashboard.upcoming || []), ...pending.filter(s => !today || s.work_date >= today)]);
        const serverWeek = (copy.dashboard.upcoming || []).filter(s => weekStart && inRange(s, weekStart, weekEnd));
        const counted = serverWeek.filter(shift => !/\[Align cover: given\b/i.test(shift.notes || ''));
        const total = Math.round(counted.reduce((sum, shift) => sum + Number(shift.hours || 0), 0) * 100) / 100;
        const contracted = Number(copy.settings?.contracted_hours || 0);
        const rate = Number(copy.settings?.rate_of_pay || 0);
        copy.dashboard.summary = {
          ...(copy.dashboard.summary || {}),
          week_hours: total,
          shift_count: serverWeek.length,
          regular_hours: contracted > 0 ? Math.round(Math.min(total, contracted) * 100) / 100 : total,
          overtime_hours: contracted > 0 ? Math.round(Math.max(0, total - contracted) * 100) / 100 : 0,
          pay_estimate: rate > 0 ? Math.round(total * rate * 100) / 100 : 0,
          contracted_hours: contracted,
          rate_of_pay: rate,
        };
      }
      return copy;
    }

    if (path.startsWith('/api/week')) {
      const start = copy.start, end = copy.end;
      copy.shifts = uniqueShifts([...(copy.shifts || []), ...pending.filter(s => inRange(s, start, end))]);
      const busyStart = start ? addDays(start, -1) : start, busyEnd = end ? addDays(end, 1) : end;
      copy.busy_shifts = uniqueShifts([...(copy.busy_shifts || []), ...pending.filter(s => inRange(s, busyStart, busyEnd))]);
      return copy;
    }

    if (path.startsWith('/api/month')) {
      copy.shifts = uniqueShifts([...(copy.shifts || []), ...pending.filter(s => inRange(s, copy.start, copy.end))]);
      return copy;
    }

    if (path.startsWith('/api/shifts?')) {
      const url = new URL(path, window.location.origin);
      const start = url.searchParams.get('start'), end = url.searchParams.get('end');
      return uniqueShifts([...(Array.isArray(copy) ? copy : []), ...pending.filter(s => inRange(s, start, end))]);
    }
    const sectionMatch = path.match(/^\/api\/sections\/(\d+)$/);
    if (sectionMatch) {
      const extras = await pendingOrganiserEvents(Number(sectionMatch[1]));
      copy.events = [...(copy.events || []), ...extras].sort((a,b) => `${a.start_at} ${a.title}`.localeCompare(`${b.start_at} ${b.title}`));
      return copy;
    }
    return copy;
  }

  async function cached(path) {
    const payload = await getCache(path);
    return payload === null ? null : overlay(path, payload);
  }

  async function remember(path, payload) {
    await putCache(path, payload);
    return overlay(path, payload);
  }

  async function flush(send) {
    let flushed = 0;
    for (const item of await listOutbox()) {
      try {
        await send(item.path, { method: item.method, body: item.body });
        await removeOutbox(item.requestId);
        flushed += 1;
      } catch (error) {
        if (error?.serverResponse) {
          // A server validation/conflict error needs the user's attention; keep it queued.
          return { flushed, blocked: true, error };
        }
        return { flushed, blocked: false, error };
      }
    }
    return { flushed, blocked: false, error: null };
  }

  async function pendingCount() { return (await listOutbox()).length; }

  async function cacheEntries() {
    const db = await openDb();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(CACHE_STORE, 'readonly');
        const request = tx.objectStore(CACHE_STORE).getAll();
        request.onsuccess = () => resolve((request.result || []).map(item => ({ key: item.key, savedAt: item.savedAt || 0 })));
        request.onerror = () => reject(request.error || new Error('Unable to inspect offline cache.'));
      });
    } finally { db.close(); }
  }

  async function diagnostics(requiredKeys = []) {
    try {
      const entries = await cacheEntries();
      const keys = entries.map(item => item.key);
      return {
        indexedDb: true,
        cachedKeys: keys,
        required: requiredKeys.map(key => ({ key, ready: keys.includes(key) })),
        pending: await pendingCount(),
      };
    } catch (error) {
      return { indexedDb: false, cachedKeys: [], required: requiredKeys.map(key => ({ key, ready: false })), pending: 0, error: String(error?.message || error) };
    }
  }

  async function reset() {
    await new Promise((resolve, reject) => {
      const request = indexedDB.deleteDatabase(DB_NAME);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error || new Error('Unable to clear offline data.'));
      request.onblocked = () => resolve();
    });
  }

  return { cached, remember, queueShiftBatch, queueOrganiserEvent, flush, pendingCount, diagnostics, reset };
})();

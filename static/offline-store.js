// Align offline-first browser storage.
// Keeps a local cache of successful API reads and an outbox of Section events
// created while the Python/SQLite server cannot be reached. Legacy shift batches
// already in IndexedDB are retained for recovery, but are never replayed.
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

  function stableNegativeId(requestId, index) {
    let hash = 2166136261;
    const text = `${requestId}:${index}`;
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return -Math.max(1, Math.abs(hash | 0));
  }

  function addDays(iso, count) {
    const value = new Date(`${iso}T12:00:00`);
    value.setDate(value.getDate() + count);
    const y = value.getFullYear(), m = String(value.getMonth() + 1).padStart(2, '0'), d = String(value.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
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

  async function overlay(path, payload) {
    if (!payload || typeof payload !== 'object') return payload;
    const sectionMatch = path.match(/^\/api\/sections\/(\d+)$/);
    if (!sectionMatch) return payload;
    const extras = await pendingOrganiserEvents(Number(sectionMatch[1]));
    if (!extras.length) return payload;
    const copy = typeof structuredClone === 'function' ? structuredClone(payload) : JSON.parse(JSON.stringify(payload));
    copy.events = [...(copy.events || []), ...extras].sort((a,b) => `${a.start_at} ${a.title}`.localeCompare(`${b.start_at} ${b.title}`));
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
      // Do not send retired shift batches to the V3 API or discard them silently.
      // They stay in local IndexedDB for explicit recovery/export.
      if (item.kind === 'shift-batch') continue;
      try {
        await send(item.path, { method: item.method, body: item.body });
        await removeOutbox(item.requestId);
        flushed += 1;
      } catch (error) {
        if (error?.serverResponse) return { flushed, blocked: true, error };
        return { flushed, blocked: false, error };
      }
    }
    return { flushed, blocked: false, error: null };
  }

  async function pendingCount() {
    return (await listOutbox()).filter(item => item.kind !== 'shift-batch').length;
  }

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
        legacyPending: (await listOutbox()).filter(item => item.kind === 'shift-batch').length,
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

  return { cached, remember, queueOrganiserEvent, flush, pendingCount, diagnostics, reset };
})();

// Week booking is a local draft until Confirm. No Rest Day is written as an event.
function addDays(day, offset) { const value = fromIso(day); value.setDate(value.getDate() + offset); return toIso(value); }
function weekDates(start) { return Array.from({length: 7}, (_, i) => addDays(start, i)); }
function wcLabel(start) { return `W/C Monday ${prettyDate(start, {day: 'numeric', month: 'long', year: 'numeric'})}`; }
function safeColour(value, fallback = '#365CE6') { return /^#[0-9a-f]{6}$/i.test(value || '') ? value : fallback; }
function datedBounds(shift) {
  const start = new Date(`${shift.work_date}T${shift.start_time}`);
  const end = new Date(`${shift.work_date}T${shift.end_time}`);
  if (end <= start) end.setDate(end.getDate() + 1);
  return [start, end];
}
function datedOverlap(a, b) { const [s,e] = datedBounds(a), [t,u] = datedBounds(b); return s < u && t < e; }
function overlapsImported(shift, event) { const [s,e] = datedBounds(shift); return s < new Date(event.end_at) && new Date(event.start_at) < e; }
function shiftCountsForPay(shift) { return !/\[Align cover: given\b/i.test(shift?.notes || ''); }
function weekPaySummary(shifts, settings = {}) {
  const prefs = settings || {};
  const counted = (shifts || []).filter(shiftCountsForPay);
  const total = Math.round(counted.reduce((sum, shift) => sum + Number(shift.hours || 0), 0) * 100) / 100;
  const contracted = Number(prefs.contracted_hours || 0);
  const rate = Number(prefs.rate_of_pay || 0);
  const overtime = contracted > 0 ? Math.round(Math.max(0, total - contracted) * 100) / 100 : 0;
  const regular = contracted > 0 ? Math.round(Math.min(total, contracted) * 100) / 100 : total;
  return {week_hours: total, shift_count: (shifts || []).length, regular_hours: regular, overtime_hours: overtime, pay_estimate: rate > 0 ? Math.round(total * rate * 100) / 100 : 0, contracted_hours: contracted, rate_of_pay: rate};
}
function weekTotalsText(shifts, settings) {
  const summary = weekPaySummary(shifts, settings || {});
  const parts = [`${summary.shift_count} shifts`, hours(summary.week_hours)];
  if (summary.contracted_hours > 0) parts.push(`${hours(summary.overtime_hours)} over ${hours(summary.contracted_hours)}`);
  if (summary.pay_estimate > 0) parts.push(`about £${summary.pay_estimate.toFixed(2)}`);
  return parts.join(' · ');
}
function restGapWarnings(shifts, minimum) {
  const gap = Number(minimum || 0);
  if (!gap) return [];
  const ordered = [...(shifts || [])].filter(shift => shift.start_time && shift.end_time && shift.work_date).sort((a, b) => `${a.work_date}T${a.start_time}`.localeCompare(`${b.work_date}T${b.start_time}`));
  const warnings = [];
  for (let index = 1; index < ordered.length; index += 1) {
    const between = (datedBounds(ordered[index])[0] - datedBounds(ordered[index - 1])[1]) / 3600000;
    if (between < gap) warnings.push(`${prettyDate(ordered[index].work_date, {weekday:'short', day:'numeric', month:'short'})} starts ${between <= 0 ? 'without a break' : `${between.toFixed(1)}h`} after the previous shift. Your rest setting is ${gap}h.`);
  }
  return warnings;
}
function savedLeaveLine(notes = '') {
  const match = String(notes || '').match(/Leave (?:home|current location): [^\n]+/i) || String(notes || '').match(/Leave(?: home| current location)?: \d{1,2}:\d{2}/);
  return match ? match[0].trim() : '';
}
function typeBadge(name, colour) {
  const c = safeColour(colour, '#3B82F6');
  return `<span class="area-badge" style="--area-colour:${c}"><span aria-hidden="true" class="area-dot"></span>${escapeHtml(name)}</span>`;
}
function basicJourneyTimes(notes = '') {
  const block = String(notes).match(/\[Align travel\]([\s\S]*?)(?:\[\/Align travel\]|$)/i);
  if (!block) return '';
  const lines = block[1].split(/\r?\n/).map(s => s.trim());
  const time = line => (String(line || '').match(/\b([01]?\d|2[0-3]):[0-5]\d\b/) || [])[0] || '';
  const leave = time(lines.find(s => /^Leave\b/i.test(s)));
  const arrival = time(lines.find(s => /^Arrive\b/i.test(s)));
  const services = travelSteps(notes).filter(s => ['bus', 'train', 'rail', 'tram'].includes(s.mode)).map(s => { const time = journeyClock(s.expected_start || s.start); return time ? `${s.mode === 'bus' ? 'Bus' : 'Train'}: ${time}` : ''; }).filter(Boolean);
  return [leave && `Leave: ${leave}`, ...services, arrival && `Arrive: ${arrival}`].filter(Boolean).join(' · ');
}
function journeyTimeIcons(notes = '') {
  const block=String(notes).match(/\[Align travel\]([\s\S]*?)(?:\[\/Align travel\]|$)/i);
  if(!block)return '';
  const lines=block[1].split(/\r?\n/).map(s=>s.trim());
  const getTime=line=>(String(line||'').match(/\b([01]?\d|2[0-3]):[0-5]\d\b/)||[])[0]||'';
  const items=[];
  const leave=getTime(lines.find(s=>/^Leave\b/i.test(s)));
  if(leave)items.push({kind:'leave',label:'Leave at',time:leave});
  for(const step of travelSteps(notes).filter(s=>['bus','train','rail','tram'].includes(s.mode))){
    const time=journeyClock(step.expected_start||step.start);
    if(time)items.push({kind:'transit',label:step.mode==='bus'?'Bus due at':'Train due at',time,step});
  }
  const arrival=getTime(lines.find(s=>/^Arrive\b/i.test(s)));
  if(arrival)items.push({kind:'arrive',label:'Arrive at',time:arrival});
  return items.map(item=>{
    const art=item.kind==='transit'
      ? journeyModeArtwork(item.step,48)
      : `<span class="journey-mode-art" style="--journey-icon-size:40px"><img src="/journey-icons/${item.kind==='arrive'?'arrival':'walking'}.png" alt="" aria-hidden="true"></span>`;
    return `<span class="journey-time-icon" title="${escapeHtml(item.label)}">${art}<span class="journey-time-copy"><small>${escapeHtml(item.label)}</small><strong>${escapeHtml(item.time)}</strong></span></span>`;
  }).join('');
}
function displayTravelNotes(notes = '') {
  const text = basicJourneyTimes(notes) || String(notes).replace(/\[Align travel(?: steps)?\][\s\S]*?(?:\[\/Align travel(?: steps)?\]|$)/ig, '').replace(/\[Align travel reminder:[^\]]*\]/ig, '').trim();
  return typeof formatDatesInText === 'function' ? formatDatesInText(text) : text;
}
function travelSteps(notes = '') {
  const match = String(notes || '').match(/\[Align travel steps\]([\s\S]*?)\[\/Align travel steps\]/i);
  if (match) {
    try { const steps = JSON.parse(match[1]); if (Array.isArray(steps)) return steps; } catch (_) {}
  }
  const block = String(notes || '').match(/\[Align travel\]([\s\S]*?)(?:\[\/Align travel\]|$)/i);
  if (!block) return [];
  return block[1].split(/\r?\n/).map(line => {
    const item = line.match(/^(Walk|Bus|Train|Tram|Rail)\s*([^·]*)·\s*(\d+)\s*min\s*·\s*([^·]+)\s*·\s*(.*?)\s*→\s*(.*?)\s*$/i);
    if (!item) return null;
    const mode = item[1].toLowerCase() === 'rail' ? 'train' : item[1].toLowerCase();
    return {mode, service: item[2].trim(), minutes: Number(item[3]), start: item[4].trim(), from: item[5].trim(), to: item[6].trim()};
  }).filter(Boolean);
}
function travelCard(notes = '') {
  if(String(notes).includes('[Align travel pending]'))return '<details class="compact-event-details"><summary>Journey details</summary><p class="helper">Travel is being refreshed for the updated details.</p></details>';
  const icons = journeyTimeIcons(notes);
  if (icons) return `<details class="compact-event-details"><summary>Journey details</summary><div class="event-notes travel-information journey-time-icons">${icons}</div></details>`;
  const leave = savedLeaveLine(notes);
  const text = displayTravelNotes(notes);
  const leaveHtml = leave ? `<p class="helper">${escapeHtml(leave)}</p>` : '';
  if (leaveHtml) return leaveHtml + (isAdmin && text && text !== leave ? `<div class="event-notes travel-information">${escapeHtml(text).replace(/\n/g, '<br>')}</div>` : '');
  return text && isAdmin ? `<div class="event-notes travel-information">${escapeHtml(text).replace(/\n/g, '<br>')}</div>` : '';
}
function coverLabel(notes = '') {
  const match = String(notes || '').match(/\[Align cover: (given|extra)(?:\s+([^\]]+))?\]/i);
  if (!match) return '';
  const who = (match[2] || '').trim();
  const title = match[1].toLowerCase() === 'given' ? 'Given away' : 'Extra cover';
  return who ? `${title} · ${who}` : title;
}
function shiftCard(shift, showDate) {
  const locationColour = safeColour(state.boot.master.locations.find(l => l.id === shift.location_id)?.colour || shift.location_colour || shift.colour);
  const areaOnly = typeof eventChoice === 'function' && eventChoice('title_format', 'location_area') === 'area';
  const badge = areaOnly ? '' : typeBadge(shift.location_name, locationColour);
  const travel = typeof eventTravelMarkup === 'function' ? eventTravelMarkup(shift) : travelCard(shift.notes);
  const edit = shift.pending_sync
    ? '<span class="sync-badge">Saved offline</span>'
    : `<button class="small-button" data-shift="${shift.id}" aria-label="Edit ${escapeHtml(shift.location_name)} ${escapeHtml(shift.shift_type_name)} on ${shift.work_date}">Edit</button>`;
  return `<article class="card week-event-row event-condensed shift-event${shift.pending_sync ? '' : ' is-clickable'}" ${shift.pending_sync ? '' : `data-shift="${shift.id}" tabindex="0" role="button" aria-label="Open ${escapeHtml(shift.location_name)} on ${shift.work_date}"`} style="--section-colour:${locationColour}">
      <div class="week-event-time">${escapeHtml(shift.start_time)}–${escapeHtml(shift.end_time)}${showDate ? `<small>${escapeHtml(prettyDate(shift.work_date))}</small>` : ''}</div>
      <div><strong>${escapeHtml(shift.shift_type_name)}</strong>${badge}${coverLabel(shift.notes) ? `<small>${escapeHtml(coverLabel(shift.notes))}</small>` : ''}${travel}${edit}</div></article>`;
}
function sameLocationGroups(shifts) {
  if (typeof eventChoice === 'function' && eventChoice('location_banner', 'on') === 'off') {
    return shifts.map(shift => ({ key: '', shifts: [shift] }));
  }
  const groups = [];
  for (const shift of [...shifts].sort((a, b) => String(a.start_time).localeCompare(String(b.start_time)) || String(a.end_time).localeCompare(String(b.end_time)))) {
    const key = String(shift.location_id || shift.location_name || '').trim().toLowerCase();
    const last = groups[groups.length - 1];
    if (last && key && last.key === key) last.shifts.push(shift);
    else groups.push({ key, shifts: [shift] });
  }
  return groups;
}
function renderShiftSpan(group, showDate) {
  const cards = group.shifts.map(shift => shiftCard(shift, showDate)).join('');
  if (group.shifts.length < 2) return cards;
  const first = group.shifts[0];
  const last = group.shifts[group.shifts.length - 1];
  const colour = safeColour(state.boot.master.locations.find(l => l.id === first.location_id)?.colour || first.location_colour || first.colour);
  const areas = [...new Set(group.shifts.map(shift => shift.shift_type_name).filter(Boolean))];
  const areaOnly = typeof eventChoice === 'function' && eventChoice('title_format', 'location_area') === 'area';
  const badge = areaOnly ? '' : typeBadge(first.location_name, colour);
  const title = areas.length === 1 ? areas[0] : first.location_name;
  return `<section class="location-banner" style="--section-colour:${colour}"><div class="location-banner-head"><div class="week-event-time">${escapeHtml(first.start_time)}–${escapeHtml(last.end_time)}</div><div><strong>${escapeHtml(title)}</strong>${badge}</div></div><div class="location-banner-items">${cards}</div></section>`;
}
function renderShiftList(shifts, showDate = false) {
  return `<div class="shift-list">${sameLocationGroups(shifts).map(group => renderShiftSpan(group, showDate)).join('')}</div>`;
}
async function loadAddWeek() {
  const draft = state.add, week = draft.weekStart;
  draft.contextLoading = true;
  try {
    const data = await api(`/api/week?start=${week}`);
    if (state.add !== draft || state.add.weekStart !== week) return;
    draft.context = data; draft.contextWeek = week; draft.error = '';
  } catch (error) { if (state.add === draft) draft.error = error.message; }
  finally {
    if (state.add === draft) {
      draft.contextLoading = false;
      if (draft.selectedDate && !draft.activeDay) {
        draft.activeDay = draft.selectedDate;
        const editor = makeDayEditor(draft.selectedDate);
        if (editor) draft.editors[draft.selectedDate] = editor;
      }
      if (state.tab === 'add') render();
    }
  }
}
function renderAdd() {
  if (!state.boot.master.templates.length) return '<section class="page"><h1>Set up your shift choices first</h1><p>Enter your hours, areas and locations once, then reuse them every week.</p><button class="primary-button" data-action="work-setup">Start Work Settings</button></section>';
  const draft = state.add;
  if (!draft.weekStart) {
    draft.weekStart = state.boot.week_options[0]?.date || toIso(monday());
    draft.selectedDate = draft.weekStart;
  }
  if (!draft.context && !draft.contextLoading && !draft.error) void loadAddWeek();
  const weeks = state.boot.week_options.some(w => w.date === draft.weekStart) ? state.boot.week_options : [{date:draft.weekStart,display:wcLabel(draft.weekStart)}, ...state.boot.week_options];
  return `<section class="page week-booking"><div class="add-head"><p class="eyebrow">${draft.step === 1 ? '1. Build your week' : '2. Check & confirm'}</p><h1>${draft.step === 1 ? 'Add shifts' : 'Week summary'}</h1><p class="subtle">${draft.step === 1 ? 'Open a day, choose its shifts, then add them to the day. Only one day stays open at a time.' : 'Check all seven days. Edit any day before confirming.'}</p></div>
    <div class="button-row" aria-label="Browse rota weeks"><button class="secondary-button" data-week-action="choose-week" data-week="${addDays(draft.weekStart, -7)}" ${draft.saving ? 'disabled' : ''}>← Previous week</button><strong>${escapeHtml(wcLabel(draft.weekStart))}</strong><button class="secondary-button" data-week-action="choose-week" data-week="${addDays(draft.weekStart, 7)}" ${draft.saving ? 'disabled' : ''}>Next week →</button></div>
    <p class="helper">Start with the week after your latest rota. Use Previous week or choose any date to add or edit earlier shifts.</p>
    <div class="week-scroller" aria-label="Choose week">${weeks.map(week => `<button class="week-choice ${week.date === draft.weekStart ? 'selected' : ''}" data-week-action="choose-week" data-week="${week.date}" aria-pressed="${week.date === draft.weekStart}" ${draft.saving ? 'disabled' : ''}><strong>W/C Monday</strong><span>${escapeHtml(prettyDate(week.date, {day:'numeric',month:'short',year:'numeric'}))}</span></button>`).join('')}<label class="week-date-choice">Choose any date<input type="date" data-week-date value="${escapeHtml(draft.selectedDate || draft.weekStart)}" ${draft.saving ? 'disabled' : ''}><small>Pick a date outside the suggested rota weeks; Align will open that date for adding a shift.</small></label></div>
    <div class="button-row"><button class="secondary-button" data-week-action="fill-pattern" ${draft.saving ? 'disabled' : ''}>Use my usual days</button><button class="secondary-button" data-week-action="repeat-last" ${draft.saving ? 'disabled' : ''}>Repeat last week</button></div>
    ${draft.error ? `<div class="planner-error" role="alert">${escapeHtml(draft.error)}${!draft.context ? '<button class="small-button" data-week-action="retry-add">Retry</button>' : ''}</div>` : ''}
    ${draft.contextLoading ? '<p class="empty" role="status">Checking this week’s calendar…</p>' : !draft.context ? '' : draft.step === 1 ? renderDayList() : renderWeekReview()}</section>`;
}
function savedForDay(day) { return (state.add.context?.shifts || []).filter(s => s.work_date === day); }
function leaveForDay(day) { return state.add.context?.annual_leave.find(l => l.leave_date === day); }
function dayStateLabel(day) {
  const count = (state.add.assignments[day] || []).length;
  if (count) return `${count} shift${count === 1 ? '' : 's'} added`;
  if (leaveForDay(day)) return 'Annual leave';
  if (savedForDay(day).length) return 'Already in calendar';
  return 'Rest Day';
}
function draftLine(shift, day, index) {
  const t = state.boot.master.templates.find(t => t.id === shift.template_id);
  return `<div class="draft-item"><div><strong>${escapeHtml(t?.location_name || 'Location')}</strong>${typeBadge(t?.shift_type_name || 'Shift', state.boot.master.shift_types.find(s => s.id === t?.shift_type_id)?.colour)}<small>${escapeHtml(shift.start_time)}–${escapeHtml(shift.end_time)}</small>${displayTravelNotes(shift.notes) ? `<small>${escapeHtml(displayTravelNotes(shift.notes)).replace(/\n/g, '<br>')}</small>` : ''}</div><div class="draft-item-actions"><button class="small-button" data-week-action="edit-draft" data-day="${day}" data-index="${index}" aria-label="Edit shift ${index + 1} on ${day}">Edit</button><button class="text-button" data-week-action="remove-draft" data-day="${day}" data-index="${index}" aria-label="Remove shift ${index + 1} on ${day}">Remove</button></div></div>`;
}
function makeDayEditor(day, index = null) {
  const original = index === null ? null : state.add.assignments[day][index];
  const options = availableDraftTemplates(day, index);
  if (!options.length) return null;
  const template = options.find(t => t.id === original?.template_id) || options[0];
  return {index, templateId: template.id, notes: original?.notes || '', reminder: travelReminderMinutes(original?.notes)};
}
function renderDayEditor(day) {
  const editor = state.add.editors[day];
  if (!editor) return '';
  const options = availableDraftTemplates(day, editor.index);
  const selected = options.find(t => t.id === editor.templateId);
  if (!selected) return `<div class="planner-error">That choice is no longer compatible with your week. Cancel it and choose again.<button class="small-button" data-week-action="cancel-editor" data-day="${day}">Cancel choice</button></div>`;
  const atLocation = options.filter(t => t.location_id === selected.location_id);
  const groupKey = t => `${t.shift_type_id}:${areaHasBothPeriods(t) ? shiftPeriod(t) : ''}`;
  const areas = [...new Map(atLocation.map(t => [groupKey(t), t])).values()];
  const atArea = atLocation.filter(t => groupKey(t) === groupKey(selected));
  const locations = [...new Map(options.map(t => [t.location_id, t])).values()];
  return `<form class="day-editor" data-week-form="day" data-day="${day}"><h3>${editor.index === null ? 'Add a shift' : 'Edit this shift'}</h3>
    <label class="field">Location<select data-day-field="location" data-day="${day}">${locations.map(t => `<option value="${t.location_id}" ${t.location_id === selected.location_id ? 'selected' : ''}>${escapeHtml(t.location_name)}</option>`).join('')}</select></label>
    ${areas.length > 1 ? `<label class="field">Shift type / area<select data-day-field="area" data-day="${day}">${areas.map(t => `<option value="${groupKey(t)}" ${groupKey(t) === groupKey(selected) ? 'selected' : ''}>${escapeHtml(areaLabel(t))}</option>`).join('')}</select></label>` : `<p class="single-area">${escapeHtml(areaLabel(selected))}</p>`}
    <label class="field">Start time + shift duration<select data-day-field="time" data-day="${day}">${atArea.map(t => `<option value="${t.id}" ${t.id === selected.id ? 'selected' : ''}>${escapeHtml(savedTimeLabel(t))}</option>`).join('')}</select></label>
    <p class="helper">${escapeHtml(templateSummary(selected))}</p>${isAdmin?`<label class="field">Notes (optional)<textarea data-day-notes="${day}">${escapeHtml(editor.notes)}</textarea></label>`:''}
    ${travelReminderFields(travelReminderNotes(editor.notes,editor.reminder))}<div class="button-row"><button type="button" class="secondary-button" data-week-action="cancel-editor" data-day="${day}">Cancel choice</button><button class="primary-button">${editor.index === null ? 'Add to day' : 'Save day change'}</button></div></form>`;
}
function renderDayList() {
  return `<div class="day-accordion">${weekDates(state.add.weekStart).map(day => {
    const shifts = state.add.assignments[day] || [], open = state.add.activeDay === day;
    return `<section class="card day-section"><h2><button class="day-heading" data-week-action="toggle-day" data-day="${day}" aria-expanded="${open}" aria-controls="day-panel-${day}"><span><strong>${weekdayName(day)}</strong><small>${escapeHtml(prettyDate(day, {day:'numeric', month:'short'}))}</small></span><span class="day-status ${shifts.length ? 'day-done' : ''}">${shifts.length ? '<b aria-hidden="true">✓</b> ' : ''}${dayStateLabel(day)}</span><span aria-hidden="true">${open ? '⌃' : '⌄'}</span></button></h2>
      ${open ? `<div id="day-panel-${day}" class="day-panel">${savedForDay(day).length ? `<p class="helper">Already saved in this week:</p>${renderShiftList(savedForDay(day))}` : ''}${shifts.map((s,i) => draftLine(s, day, i)).join('')}${renderDayEditor(day)}${!state.add.editors[day] ? `<button class="secondary-button" data-week-action="new-editor" data-day="${day}" ${availableDraftTemplates(day).length ? '' : 'disabled'}>${shifts.length || savedForDay(day).length ? '＋ Add another shift' : '＋ Add shift'}</button>` : ''}${!availableDraftTemplates(day).length && !state.add.editors[day] ? `<p class="helper">${leaveForDay(day) ? 'This day is booked as annual leave.' : 'No further compatible shifts for this day. AM/PM, hours, appointments and calendar clashes are checked.'}</p>` : ''}</div>` : ''}</section>`;
  }).join('')}</div><p class="helper">A green tick means added to this draft, not yet saved to the calendar. Unused days stay Rest Days.</p><div class="button-row"><button class="primary-button" data-week-action="review">Next · Week summary</button></div>`;
}
function reviewShiftRows() {
  const drafts = assignedShifts().map(shift => {
    const template = state.boot.master.templates.find(item => item.id === shift.template_id);
    const gross = timeHours(shift.start_time, shift.end_time);
    return {...shift, hours: Math.max(0, gross - Number(shift.break_minutes || template?.break_minutes || 0) / 60)};
  });
  return [...(state.add.context?.shifts || []), ...drafts];
}
function fillUsualWeek() {
  if (!state.add.context) throw new Error('Wait for this week to finish loading.');
  const draft = state.add;
  let added = 0;
  for (const day of weekDates(draft.weekStart)) {
    if (leaveForDay(day)) continue;
    for (const period of ['AM', 'PM']) {
      const matches = state.boot.master.templates.filter(template => template.active && templateAppliesOn(template, day) && shiftPeriod(template) === period);
      if (matches.length !== 1) continue;
      if (!availableDraftTemplates(day).some(template => template.id === matches[0].id)) continue;
      draft.assignments[day] = [...(draft.assignments[day] || []), draftFor(matches[0], day)];
      added += 1;
    }
  }
  draft.requestId = null;
  if (!added) throw new Error('No usual day could be filled. Check the weekdays in Work Settings, plus leave and clashes.');
}
async function repeatLastWeek() {
  if (!state.add.context) throw new Error('Wait for this week to finish loading.');
  const previous = await api(`/api/week?start=${addDays(state.add.weekStart, -7)}`);
  let added = 0;
  for (const shift of previous.shifts || []) {
    const day = addDays(shift.work_date, 7);
    if (!weekDates(state.add.weekStart).includes(day) || leaveForDay(day)) continue;
    const template = state.boot.master.templates.find(item => item.id === shift.template_id && item.active);
    if (!template || !availableDraftTemplates(day).some(item => item.id === template.id)) continue;
    state.add.assignments[day] = [...(state.add.assignments[day] || []), draftFor(template, day)];
    added += 1;
  }
  state.add.requestId = null;
  if (!added) throw new Error('Last week has no shifts that fit this week.');
}
function renderWeekReview() {
  return `<div class="card week-review">${weekDates(state.add.weekStart).map(day => {
    const drafts = state.add.assignments[day] || [], saved = savedForDay(day), leave = leaveForDay(day);
    return `<section class="week-review-day"><div class="section-head"><h2>${escapeHtml(dayHeading(day))}</h2><button class="small-button" data-week-action="edit-day" data-day="${day}" aria-label="Edit ${weekdayName(day)}" ${state.add.saving ? 'disabled' : ''}>Edit</button></div>${[...saved.map(s => ({...s,saved:true})), ...drafts].map(s => {
      const t = state.boot.master.templates.find(t => t.id === s.template_id);
      return `<p class="review-shift"><strong>${escapeHtml(s.shift_type_name || t?.shift_type_name)} · ${escapeHtml(s.location_name || t?.location_name)}</strong><span>${escapeHtml(s.start_time)}–${escapeHtml(s.end_time)}${s.saved ? ' · Already saved' : ''}</span></p>`;
    }).join('') || `<p class="rest-day">${leave ? 'Annual leave' : 'No shifts'}</p>`}${weekEventRows(state.add.context,day)}</section>`;
  }).join('')}</div><p class="week-totals">${escapeHtml(weekTotalsText(reviewShiftRows(), state.boot?.settings || {}))}</p>${restGapWarnings(reviewShiftRows(), state.boot?.settings?.minimum_rest_hours).map(warning => `<p class="planner-error" role="status">${escapeHtml(warning)}</p>`).join('')}<p class="helper">Confirm adds ${assignedShifts().length} new shift${assignedShifts().length === 1 ? '' : 's'} to Align’s calendar and its subscription feed. Rest Days are not events. Your external calendar updates when it refreshes the subscription.</p><div class="button-row"><button class="secondary-button" data-week-action="back" ${state.add.saving ? 'disabled' : ''}>Back</button><button class="primary-button" data-week-action="confirm" ${state.add.saving || !assignedShifts().length ? 'disabled' : ''}>${state.add.saving ? 'Saving…' : 'Confirm'}</button></div>`;
}
let scheduleRequest = 0;
async function loadScheduleWeek(day) {
  const request = ++scheduleRequest;
  state.scheduleView = 'week'; state.scheduleFocus = day;
  state.scheduleWeek = toIso(monday(fromIso(day))); state.scheduleLoading = true; state.scheduleError = ''; render();
  try {
    const result = await api(`/api/week?start=${state.scheduleWeek}`);
    if (request !== scheduleRequest) return;
    state.scheduleData = result; state.scheduleShifts = result.shifts;
  } catch (error) { if (request === scheduleRequest) state.scheduleError = error.message; }
  finally { if (request === scheduleRequest) { state.scheduleLoading = false; if (['calendar','planner'].includes(state.tab)) render(); } }
}
function renderCalendar() {
  if (['month','list'].includes(state.scheduleView)) return renderMonthCalendar();
  const data = state.scheduleData?.start === state.scheduleWeek ? state.scheduleData : null;
  return `<section class="page"><div class="add-head"><p class="eyebrow">Your calendar</p><h1>Calendar</h1><p class="subtle">Your personal and imported events, organised by date.</p></div>${scheduleViewSwitch()}
    <div class="schedule-week-nav"><button class="secondary-button" data-week-action="schedule-prev" aria-label="Previous week">‹</button><h2>${escapeHtml(wcLabel(state.scheduleWeek))}</h2><button class="secondary-button" data-week-action="schedule-next" aria-label="Next week">›</button></div>
    <div class="schedule-week-tools"><label class="field">Go to week<input type="date" data-schedule-date value="${state.scheduleWeek}"></label><button class="small-button" data-week-action="schedule-today">This week</button></div>

    ${state.scheduleError ? `<div class="planner-error" role="alert">${escapeHtml(state.scheduleError)}<button class="small-button" data-week-action="schedule-retry">Retry</button></div>` : state.scheduleLoading ? '<p role="status" class="empty">Loading week…</p>' : data ? `${weekDates(data.start).map(day => {
      const events = weekEventsForDay(data,day);
      return `<section class="schedule-day"><h2>${escapeHtml(dayHeading(day))}</h2>${events.length ? weekEventRows(data,day) : '<p class="rest-day">No events</p>'}</section>`;
    }).join('')}` : '<p class="empty">Choose a week to load your calendar.</p>'}
    </section>`;
}
function renderUserColours() {
  return `<form class="card settings-form" data-week-form="colours"><h2>Location & area colours</h2><p class="helper">Choose a left-hand location stripe and an area badge colour. Names remain visible, so you don’t have to rely on colour alone.</p>
    <h3>Locations · left stripe</h3>${state.boot.master.locations.map(l => `<label class="colour-setting"><span>${escapeHtml(l.name)}</span><input type="color" data-colour-location="${l.id}" value="${safeColour(l.colour)}" aria-label="${escapeHtml(l.name)} location colour"></label>`).join('') || '<p class="helper">Add your first location in Work Settings.</p>'}
    <h3>Shift types / areas · badge</h3>${state.boot.master.shift_types.map(t => `<label class="colour-setting"><span>${escapeHtml(t.name)}</span><input type="color" data-colour-type="${t.id}" value="${safeColour(t.colour)}" aria-label="${escapeHtml(t.name)} area colour"></label>`).join('') || '<p class="helper">Add your first area in Work Settings.</p>'}<button class="primary-button">Save colours</button></form>`;
}
function plannerError(message) { state.add.error = message; render(); document.querySelector('.planner-error')?.scrollIntoView({block:'nearest'}); }
document.addEventListener('input', event => {
  if (event.target.dataset.dayNotes) state.add.editors[event.target.dataset.dayNotes].notes = event.target.value;
});
document.addEventListener('change', event => {
  const el = event.target;
  if (el.matches('[data-week-date]') && el.value) {
    const chosenDate = el.value;
    const selected = toIso(monday(fromIso(el.value)));
    if (selected !== state.add.weekStart) {
      if ((assignedShifts().length || Object.keys(state.add.editors).length) && !window.confirm('Change week and discard this unsaved draft?')) { render(); return; }
      state.add = newAddState(); state.add.weekStart = selected; state.add.selectedDate = chosenDate; render();
    } else {
      state.add.selectedDate = chosenDate;
      state.add.activeDay = chosenDate;
      const editor = makeDayEditor(chosenDate);
      if (editor) state.add.editors[chosenDate] = editor;
      render();
    }
    return;
  }
  if (el.name === 'travel_reminder' && el.closest('[data-week-form=day]')) { state.add.editors[el.closest('form').dataset.day].reminder=el.value; return; }
  if (el.hasAttribute('data-schedule-date') && el.value) { void loadScheduleWeek(el.value); return; }
  if (!el.dataset.dayField) return;
  const day = el.dataset.day, editor = state.add.editors[day], options = availableDraftTemplates(day, editor.index);
  const current = options.find(t => t.id === editor.templateId);
  const selected = el.dataset.dayField === 'location' ? options.find(t => t.location_id === Number(el.value)) : el.dataset.dayField === 'time' ? options.find(t => t.id === Number(el.value)) : options.find(t => t.location_id === current.location_id && `${t.shift_type_id}:${areaHasBothPeriods(t) ? shiftPeriod(t) : ''}` === el.value);
  if (selected) editor.templateId = selected.id;
  render();
});
document.addEventListener('submit', async event => {
  const form = event.target;
  if (!form.dataset.weekForm) return;
  event.preventDefault();
  if (form.dataset.weekForm === 'colours') {
    const button = form.querySelector('button'); button.disabled = true;
    try { await api('/api/user-colours', {method:'PUT', body:{locations:[...form.querySelectorAll('[data-colour-location]')].map(i => ({id:Number(i.dataset.colourLocation),colour:i.value})), shift_types:[...form.querySelectorAll('[data-colour-type]')].map(i => ({id:Number(i.dataset.colourType),colour:i.value}))}}); await refresh(); toast('Colours updated.'); }
    catch (error) { toast(error.message); button.disabled = false; }
    return;
  }
  const day = form.dataset.day, editor = state.add.editors[day];
  const template = availableDraftTemplates(day, editor.index).find(t => t.id === editor.templateId);
  if (!template) { plannerError('Choose a compatible saved shift time.'); return; }
  const shift = {...draftFor(template,day),notes:travelReminderNotes(editor.notes,editor.reminder)};
  const list = state.add.assignments[day] ||= [];
  if (editor.index === null) list.push(shift); else list[editor.index] = shift;
  delete state.add.editors[day]; state.add.error = ''; state.add.requestId = null; render();
});
document.addEventListener('click', async event => {
  if (event.target.closest('.compact-event-details')) return;
  if (event.target.closest('.apple-maps-link')) return;
  if (event.target.closest('a[href^="tel:"]')) return;
  const el = event.target.closest('[data-week-action]');
  if (!el) return;
  const action = el.dataset.weekAction, day = el.dataset.day;
  if (action.startsWith('schedule-')) {
    const next = action === 'schedule-prev' ? addDays(state.scheduleWeek,-7) : action === 'schedule-next' ? addDays(state.scheduleWeek,7) : action === 'schedule-today' ? isoToday() : state.scheduleWeek;
    await loadScheduleWeek(next); return;
  }
  if (action === 'event-view') {
    const item = JSON.parse(decodeURIComponent(el.dataset.eventDetails));
    const contact = window.ALIGN152?.eventContactMarkup(item.notes) || '';
    modal(item.title || 'Event', `<div class="settings-form"><p>${escapeHtml(sectionEventDate(item))}</p>${item.location ? `<p>${appleDestinationLink(item.location)}</p>` : ''}${contact}${travelCard(item.notes || '')}<p class="helper">${item.origin === 'Calendar' ? 'Imported calendar event. Edit it in its original calendar.' : 'Event details'}</p></div>`);
    void mountPostTravelEditor(item.origin==='Calendar'?'calendar':'event',item.id);
    return;
  }
  if (action === 'event-edit' || action === 'event-travel') {
    const sectionId = Number(el.dataset.sectionId), eventId = Number(el.dataset.eventId);
    if (!sectionId || !eventId) return;
    try {
      state.sectionId = sectionId;
      state.sectionData = await api(`/api/sections/${sectionId}`);
      sectionEventModal(eventId);
      if (action === 'event-travel') {
        const details = modalRoot.querySelector('[data-form="organiser-event"] details');
        if (details) details.open = true;
        modalRoot.querySelector('[data-personal="journey"]')?.focus();
      }
    } catch (error) { toast(error.message); }
    return;
  }
  if (state.add.saving) return;
  if (action === 'choose-week') {
    if (el.dataset.week === state.add.weekStart) return;
    if ((assignedShifts().length || Object.keys(state.add.editors).length) && !window.confirm('Change week and discard this unsaved draft?')) return;
    state.add = newAddState(); state.add.weekStart = el.dataset.week; render(); return;
  }
  if (action === 'choose-date') {
    const value = el.value;
    if (!value) return;
    const selected = toIso(monday(fromIso(value)));
    if (selected === state.add.weekStart) return;
    if ((assignedShifts().length || Object.keys(state.add.editors).length) && !window.confirm('Change week and discard this unsaved draft?')) return;
    state.add = newAddState(); state.add.weekStart = selected; render(); return;
  }
  if (action === 'retry-add') { state.add.error = ''; void loadAddWeek(); render(); return; }
  if (action === 'toggle-day' || action === 'edit-day') {
    state.add.step = 1;
    state.add.activeDay = action === 'toggle-day' && state.add.activeDay === day ? '' : day;
    if (state.add.activeDay && !state.add.assignments[day]?.length && !state.add.editors[day]) {
      const editor = makeDayEditor(day); if (editor) state.add.editors[day] = editor;
    }
  }
  if (action === 'new-editor' || action === 'edit-draft') {
    const editor = makeDayEditor(day, action === 'edit-draft' ? Number(el.dataset.index) : null);
    if (editor) state.add.editors[day] = editor;
  }
  if (action === 'cancel-editor') delete state.add.editors[day];
  if (action === 'remove-draft') { state.add.assignments[day].splice(Number(el.dataset.index),1); delete state.add.editors[day]; state.add.requestId = null; }
  if (action === 'back') state.add.step = 1;
  if (action === 'fill-pattern' || action === 'repeat-last') {
    try {
      if (action === 'fill-pattern') fillUsualWeek();
      else await repeatLastWeek();
      state.add.error = '';
    } catch (error) { plannerError(error.message); return; }
  }
  if (action === 'review') {
    const pendingDay = Object.keys(state.add.editors)[0];
    if (pendingDay) { state.add.activeDay = pendingDay; plannerError(`Finish ${weekdayName(pendingDay)}: use Add to day / Save day change, or Cancel choice before continuing.`); return; }
    state.add.step = 2; state.add.error = '';
  }
  if (action === 'confirm') {
    if (!assignedShifts().length) return;
    const draft = state.add;
    draft.saving = true; draft.error = '';
    draft.requestId ||= crypto.randomUUID ? crypto.randomUUID() : `week-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    render();
    try {
      const prefs = personalPrefs();
      const shifts = assignedShifts().map(shift => ({...shift}));
      for (const shift of shifts) {
        const template = state.boot.master.templates.find(item => item.id === shift.template_id);
        const location = state.boot.master.locations.find(item => item.id === template?.location_id);
        if (!template || !location) continue;
        try {
          const journey = await api('/api/personal/journey', {method:'POST', body:{
            destination: location.address || location.name,
            arrival: `${shift.work_date}T${shift.start_time}`,
            mode: prefs.default_travel || 'transit',
            departure_buffer: Number(prefs.departure_buffer ?? 5),
            arrival_buffer: Number(prefs.arrival_buffer ?? 10)
          }});
          const plan = journey.journeys?.[0];
          if (plan?.notes) shift.notes = `${shift.notes || ''}\n[Align travel]\n${plan.notes}\n[/Align travel]${plan.steps?.length ? `\n[Align travel steps]\n${JSON.stringify(plan.steps)}\n[/Align travel steps]` : ''}`.trim();
        } catch (_) {
          // Travel is supplementary; a provider outage must not block saving a shift.
        }
      }
      const result = await api('/api/shifts', {method:'POST',body:{shifts,allow_any_date:true,request_id:draft.requestId}});
      state.scheduleWeek = draft.weekStart; state.scheduleFocus = draft.weekStart; state.scheduleView = 'week'; state.add = newAddState(); state.tab = 'calendar'; await refresh();
      toast(result?.queued ? 'Saved on this phone. Align will sync it when your PC is reachable again.' : 'Week confirmed and added to your calendar.');
    } catch (error) { if (state.add === draft) { draft.saving = false; plannerError(error.message); } else toast(error.message); }
    return;
  }
  render();
  if (action === 'review' || action === 'back') document.querySelector('.week-booking')?.scrollIntoView({block:'start'});
  if (action === 'edit-day') document.querySelector(`#day-panel-${day}`)?.scrollIntoView({block:'nearest'});
});
document.addEventListener('keydown', event => {
  const row = event.target.closest?.('.week-event-row.is-clickable, .shift-event.is-clickable');
  if (row && event.target === row && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); row.click(); }
});
window.addEventListener('beforeunload', event => { if (typeof state !== 'undefined' && (assignedShifts().length || Object.keys(state.add.editors).length)) { event.preventDefault(); event.returnValue = ''; } });

function weekEventsForDay(data,day) { const next=addDays(day,1);return [...(data?.events||[]).map(e=>({...e,origin:'Event'})),...(data?.imported_events||[]).map(e=>({...e,origin:'Calendar'}))].filter(e=>e.start_at < next && e.end_at > day+'T00:00').sort((a,b)=>a.start_at.localeCompare(b.start_at)); }
function savedTravelSummary(notes = '') {
  const text = journeyTimeIcons(notes);
  return text ? `<details class="compact-event-details"><summary>Journey details</summary><small class="event-travel-summary journey-time-icons">${text}</small></details>` : '';
}
function weekEventRows(data,day) {
  return weekEventsForDay(data,day).map((event, index) => {
    const row = typeof renderEventRow === 'function'
      ? renderEventRow(event, { day, showDate: false, index })
      : '';
    if (row) {
      const reminder = travelReminderMinutes(event.notes)
        ? `<small>Travel alert · ${travelReminderMinutes(event.notes)} min before</small>`
        : '';
      return reminder ? row.replace('</article>', `${reminder}</article>`) : row;
    }
    return '';
  }).join('');
}

function eventViewAttributes(item) {
  return ` data-week-action="event-view" data-event-details="${escapeHtml(encodeURIComponent(JSON.stringify(item)))}" tabindex="0" role="button" aria-label="Open ${escapeHtml(item.title || 'event')}"`;
}

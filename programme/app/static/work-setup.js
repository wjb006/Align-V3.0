// View first: only an explicit Add/Edit creates an unsaved draft.
let workSetup = null;
let setupCounter = 0;
const setupKey = prefix => `${prefix}-new-${Date.now()}-${++setupCounter}`;
const setupPeriod = time => time < '12:00' ? 'AM' : 'PM';
const settingsCopy = value => JSON.parse(JSON.stringify(value));
const settingsKinds = {locations: 'work location', areas: 'shift area', slots: 'start time', hours: 'working hours'};
function setupEnd(slot) {
  const [h, m] = slot.start_time.split(':').map(Number);
  const total = (h * 60 + m + Number(slot.duration_minutes)) % 1440;
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}
function setupTimeLabel(slot) {
  return `${slot.start_time} + ${hours(slot.duration_minutes / 60)} → ${setupEnd(slot)}${slot.break_minutes ? ` · ${slot.break_minutes}m break` : ''}`;
}
function setupInput(label, html) { return `<label class="field"><span>${escapeHtml(label)}</span>${html}</label>`; }
function setupButton(action, text, attributes = '') {
  return `<button type="button" class="small-button" data-settings-action="${action}" ${attributes}>${text}</button>`;
}
async function openWorkSetup() {
  try {
    workSetup = { data: await api('/api/work-setup'), editor: null, error: '', saving: false, returnTab: state.tab };
    state.tab = 'work-setup'; render();
  } catch (error) { toast(error.message); }
}
function settingsScope(a, kind, key) {
  return kind !== 'hours' && a[{locations: 'location_key', areas: 'area_key', slots: 'slot_key'}[kind]] === key;
}
function settingsAssignmentText(a, data) {
  const location = data.locations.find(i => i.key === a.location_key);
  const area = data.areas.find(i => i.key === a.area_key);
  const slot = data.slots.find(i => i.key === a.slot_key);
  return `${location?.name || 'Location'} · ${area?.name || 'Area'} · ${slot ? setupTimeLabel(slot) : 'Time'} · ${a.days.map(d => d.slice(0, 3)).join(', ')}`;
}
function renderSettingsCategory(kind, title, empty) {
  const data = workSetup.data;
  return `<details class="card settings-form ws-category" ${workSetup.category === kind ? "open" : ""}><summary>${title}<span class="ws-count">${data[kind].length} saved</span></summary><div class="section-head"><h2>${title}</h2>${setupButton('add', '+ Add', `data-kind="${kind}" aria-label="Add ${settingsKinds[kind]}"`)}</div>
    ${data[kind].map(item => {
      const assignments = data.assignments.filter(a => settingsScope(a, kind, item.key));
      const label = kind === 'slots' ? setupTimeLabel(item) : item.name;
      return `<article class="ws-list-item"><div class="ws-item-head"><div>${kind !== 'slots' ? `<span class="ws-colour-dot" style="--item-colour:${safeColour(item.colour)}" aria-hidden="true"></span>` : ''}<h3>${escapeHtml(label)}</h3></div>${setupButton('edit', 'Edit', `data-kind="${kind}" data-key="${escapeHtml(item.key)}" aria-label="Edit ${escapeHtml(label)}"`)}</div>
        ${kind === 'locations' ? `<p class="helper">${escapeHtml(item.address)}</p>` : ''}
        ${assignments.length ? `<p class="helper">${assignments.length} saved ${assignments.length === 1 ? "combination" : "combinations"}</p>` : '<p class="helper ws-pending">Choose times and days in Edit.</p>'}</article>`;
    }).join('') || `<p class="empty">${empty}</p>`}</details>`;
}
function renderWorkSetup() {
  if (!workSetup) return '';
  const data = workSetup.data;
  return `<section class="page work-settings"><div class="add-head"><p class="eyebrow">Your planner</p><h1>Work Settings</h1><p class="subtle">Choose what you want to change.</p></div>
    <div id="settings-error" role="alert" ${workSetup.error ? '' : 'hidden'}>${escapeHtml(workSetup.error)}</div>
    ${workSetup.editor ? renderSettingsEditor() : `<section class="card settings-form"><div class="section-head"><h2>Working hours</h2>${setupButton('edit', 'Edit', 'data-kind="hours" aria-label="Edit working hours"')}</div><p>${hours(data.contracted_hours)} contracted per week · ${hours(data.duration_minutes / 60)} standard duration · £${number(data.rate_of_pay)} per hour</p><p class="helper">${Number(data.leave_allowance_days) || 0} leave days from ${escapeHtml(data.leave_year_start || '01-01')}${Number(data.minimum_rest_hours) ? ` · ${data.minimum_rest_hours}h minimum rest` : ''}</p></section>
      ${renderSettingsCategory('locations', 'Work Locations', 'No work locations saved. Add your first location.')}
      ${renderSettingsCategory('areas', 'Shift Areas', 'No shift areas saved. Add a category such as Office, Remote or Customer visits.')}
      ${renderSettingsCategory('slots', 'Start Times', 'No start times saved. Add a time and duration.')}
      <p class="apply-note">Settings define the choices for future bookings. Saved shifts and calendar events keep their dates and hours.</p>
      <button class="secondary-button" data-settings-action="close">Back to ${workSetup.returnTab==='planner'?'Planner':workSetup.returnTab==='more'?'More':isAdmin?'Master edit':'Settings'}</button>`}</section>`;
}
function openSettingsEditor(kind, key) {
  const data = settingsCopy(workSetup.data);
  const existing = key && data[kind]?.find(i => i.key === key);
  if (key && !existing) throw new Error('That item is no longer available. Reopen Work Settings.');
  let item = existing;
  if (kind !== 'hours' && !item) {
    item = kind === 'slots' ? {key: setupKey('s'), start_time: '', duration_minutes: data.duration_minutes, break_minutes: 0}
      : {key: setupKey(kind === 'locations' ? 'l' : 'a'), name: '', colour: kind === 'locations' ? '#365CE6' : '#3B82F6', ...(kind === 'locations' ? {address: ''} : {slots: []})};
    data[kind].push(item);
  }
  workSetup.category = kind;
  workSetup.editor = {kind, key: item?.key, isNew: !existing && kind !== 'hours', step: 1, data};
  workSetup.error = '';
}
function renderSettingsDetails(editor) {
  const {kind, data, key} = editor;
  const item = data[kind]?.find(i => i.key === key);
  const numeric = (label, field, value, min, max, step) => setupInput(label, `<input type="number" data-settings-field="${field}" value="${value}" min="${min}" max="${max}" step="${step}" required>`);
  if (kind === 'hours') return `<div class="setup-two">${numeric('Contracted hours per week', 'contracted_hours', data.contracted_hours, 0, 168, .25)}${numeric('Standard shift duration (hours)', 'duration_minutes', data.duration_minutes / 60, .25, 23.75, .25)}${numeric('Rate of pay (£)', 'rate_of_pay', data.rate_of_pay, 0, 100000, .01)}${numeric('Leave allowance (days)', 'leave_allowance_days', data.leave_allowance_days || 0, 0, 366, 1)}${numeric('Minimum rest between shifts (hours)', 'minimum_rest_hours', data.minimum_rest_hours || 0, 0, 24, .5)}${setupInput('Leave year starts (MM-DD)', `<input data-settings-field="leave_year_start" value="${escapeHtml(data.leave_year_start || '01-01')}" pattern="[0-9]{2}-[0-9]{2}" required>`)}</div><p class="helper">Contracted hours and the hourly rate produce the weekly overtime and pay estimate. Leave allowance counts booked days in the leave year. Minimum rest warns when shifts are too close. Existing bookings are unchanged.</p>`;
  if (kind === 'slots') return `${setupInput('Start time', `<input type="time" data-settings-field="start_time" value="${escapeHtml(item.start_time)}" required>`)}<div class="setup-two">${numeric('Shift duration (hours)', 'duration_minutes', item.duration_minutes / 60, .25, 23.75, .25)}${numeric('Unpaid break (minutes)', 'break_minutes', item.break_minutes, 0, 1438, 1)}</div><p class="helper">AM / PM is automatic. Editing this time updates future choices at all linked areas and locations, not existing bookings.</p>`;
  return `${setupInput(kind === 'locations' ? 'Location name' : 'Shift area name', `<input data-settings-field="name" maxlength="80" value="${escapeHtml(item.name)}" required>`)}${setupInput(kind === 'locations' ? 'Location colour' : 'Shift area colour', `<input type="color" data-settings-field="colour" value="${safeColour(item.colour)}">`)}${kind === 'locations' ? addressFields('work-settings-address', 'address', item.address, 'Work address') : '<p class="helper">The area colour appears as a small badge. The location colour is the left-hand stripe.</p>'}`;
}
function settingsOptions(editor) {
  const {data, kind, key} = editor;
  const options = [];
  for (const location of data.locations) for (const area of data.areas) for (const slot of data.slots) {
    const option = {location_key: location.key, area_key: area.key, slot_key: slot.key};
    if (settingsScope(option, kind, key)) options.push({...option, location, area, slot});
  }
  return options;
}
function sameSettingLink(a, b) { return a.location_key === b.location_key && a.area_key === b.area_key && a.slot_key === b.slot_key; }
function renderSettingsLinks(editor) {
  const options = settingsOptions(editor), data = editor.data;
  const missing = [['locations', 'Work Location'], ['areas', 'Shift Area'], ['slots', 'Start Time']].filter(([kind]) => !data[kind].length).map(([,name]) => name);
  if (!options.length) return `<p class="apply-note">Save this item first, then add ${escapeHtml(missing.join(' and '))}. You can then edit any item to link locations, areas, times and days. No shift choices are created until they are linked.</p>`;
  return `<h3>Where and when does this apply?</h3><p class="helper">Choose the combinations you use. Open Days to change when each is available.</p>
    ${data.locations.map(location => {
      const local = options.filter(o => o.location_key === location.key);
      if (!local.length) return '';
      return `<section class="ws-link-group"><h3>${escapeHtml(location.name)}</h3>${local.map(option => {
        const index = options.indexOf(option), assigned = data.assignments.find(a => sameSettingLink(a, option));
        const label = `${option.area.name} · ${setupTimeLabel(option.slot)}`;
        return `<article class="ws-link-choice"><label class="setup-check"><input type="checkbox" data-settings-link="${index}" ${assigned ? 'checked' : ''}><span>${escapeHtml(label)}</span></label>
          ${assigned ? `<details class="ws-day-details"><summary>Days · ${assigned.days.length === 7 ? "Every day" : assigned.days.map(d => d.slice(0,3)).join(", ") || "Choose days"}</summary><fieldset class="setup-days"><legend>Days for ${escapeHtml(label)} at ${escapeHtml(location.name)}</legend>${WEEK_DAYS.map(day => `<label><input type="checkbox" data-settings-day="${index}" value="${day}" ${assigned.days.includes(day) ? 'checked' : ''}><span>${day.slice(0,3)}</span></label>`).join('')}</fieldset><div class="setup-presets">${['Weekdays', 'Weekend', 'All days'].map(preset => setupButton('days', preset, `data-option="${index}" data-preset="${preset}"`)).join('')}</div></details>` : ''}</article>`;
      }).join('')}</section>`;
    }).join('')}`;
}
function renderSettingsEditor() {
  const editor = workSetup.editor;
  return `<section class="card settings-form ws-editor" aria-label="Work Settings editor"><h2>${editor.isNew ? 'Add' : 'Edit'} ${settingsKinds[editor.kind]}</h2>
    ${renderSettingsDetails(editor)}
    ${editor.kind !== 'hours' ? `<details class="ws-optional" ${editor.isNew || editor.linksOpen ? 'open' : ''}><summary>Times, places & days</summary>${renderSettingsLinks(editor)}</details>` : ''}
    <div class="setup-footer"><button type="button" class="text-button" data-settings-action="cancel" ${workSetup.saving ? 'disabled' : ''}>Cancel</button><button type="button" class="primary-button" data-settings-action="save" ${workSetup.saving ? 'disabled' : ''}>${workSetup.saving ? 'Saving…' : 'Save changes'}</button></div></section>`;
}
function validateSettingsDetails(editor) {
  const {kind, data, key} = editor, item = data[kind]?.find(i => i.key === key);
  const validDuration = n => Number.isInteger(n) && n > 0 && n < 1440;
  if (kind === 'hours') {
    if (data.contracted_hours === '' || !Number.isFinite(data.contracted_hours) || data.contracted_hours < 0 || data.contracted_hours > 168) throw new Error('Enter contracted hours between 0 and 168.');
    if (!validDuration(data.duration_minutes)) throw new Error('Enter a standard duration shorter than 24 hours.');
    if (data.leave_allowance_days === '' || !Number.isInteger(Number(data.leave_allowance_days)) || data.leave_allowance_days < 0 || data.leave_allowance_days > 366) throw new Error('Enter a leave allowance between 0 and 366 days.');
    if (data.minimum_rest_hours === '' || !Number.isFinite(Number(data.minimum_rest_hours)) || data.minimum_rest_hours < 0 || data.minimum_rest_hours > 24) throw new Error('Enter a minimum rest between 0 and 24 hours.');
    if (!/^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.test(data.leave_year_start || '')) throw new Error('Leave year start must be a month and day, such as 04-01.');
  } else if (kind === 'slots') {
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(item.start_time)) throw new Error('Choose a start time.');
    if (!validDuration(item.duration_minutes) || !Number.isInteger(item.break_minutes) || item.break_minutes < 0 || item.break_minutes >= item.duration_minutes) throw new Error('Check the duration and break. The break must be shorter than the shift.');
    if (data.slots.some(s => s.key !== key && s.start_time === item.start_time && s.duration_minutes === item.duration_minutes && s.break_minutes === item.break_minutes)) throw new Error('This start time, duration and break are already saved. Edit the existing time instead.');
  } else {
    if (!item.name.trim()) throw new Error('Enter a name.');
    if (data[kind].some(i => i.key !== key && i.name.trim().toLowerCase() === item.name.trim().toLowerCase())) throw new Error('That name already exists. Edit its existing entry.');
    if (kind === 'locations' && !item.address.trim()) throw new Error('Enter the work address.');
  }
}
async function saveSettingsEditor() {
  const editor = workSetup.editor;
  validateSettingsDetails(editor);
  const affected = editor.data.assignments.filter(a => settingsScope(a, editor.kind, editor.key));
  if (affected.some(a => !a.days.length)) throw new Error('Select at least one day for each ticked choice.');
  if (editor.kind !== 'hours' && settingsOptions(editor).length && !affected.length) throw new Error('Tick at least one linked choice and select its days.');
  for (const a of editor.data.assignments) {
    const area = editor.data.areas.find(i => i.key === a.area_key);
    if (!area.slots.includes(a.slot_key)) area.slots.push(a.slot_key);
  }
  workSetup.saving = true; render();
  await api('/api/work-setup', {method: 'PUT', body: {...editor.data, save_mode: 'settings'}});
  workSetup.editor = null;
  workSetup.data = await api('/api/work-setup');
  workSetup.error = ''; workSetup.saving = false;
  state.add.context = null;
  await refresh();
  toast('Saved. Work Settings updated; existing bookings are unchanged.');
}
document.addEventListener('input', event => {
  if (!workSetup?.editor || state.tab !== 'work-setup' || workSetup.saving) return;
  const el = event.target, editor = workSetup.editor;
  const item = editor.kind === 'hours' ? editor.data : editor.data[editor.kind].find(i => i.key === editor.key);
  let field = el.dataset.settingsField;
  if (el.id === 'work-settings-address') field = 'address';
  if (!field) return;
  item[field] = ['contracted_hours', 'duration_minutes', 'break_minutes', 'rate_of_pay', 'leave_allowance_days', 'minimum_rest_hours'].includes(field) ? (el.value === '' ? '' : Number(el.value) * (field === 'duration_minutes' ? 60 : 1)) : el.value;
});
document.addEventListener('change', event => {
  if (!workSetup?.editor || state.tab !== 'work-setup' || workSetup.saving) return;
  const el = event.target, editor = workSetup.editor;
  if (el.dataset.settingsLink !== undefined) {
    editor.linksOpen = true;
    const option = settingsOptions(editor)[Number(el.dataset.settingsLink)];
    if (el.checked && !editor.data.assignments.some(a => sameSettingLink(a, option))) editor.data.assignments.push({location_key: option.location_key, area_key: option.area_key, slot_key: option.slot_key, days: []});
    if (!el.checked) editor.data.assignments = editor.data.assignments.filter(a => !sameSettingLink(a, option));
    render();
  }
  if (el.dataset.settingsDay !== undefined) {
    const option = settingsOptions(editor)[Number(el.dataset.settingsDay)];
    const a = editor.data.assignments.find(a => sameSettingLink(a, option));
    a.days = el.checked ? [...new Set([...a.days, el.value])] : a.days.filter(d => d !== el.value);
    el.closest('details').querySelector('summary').textContent = 'Days · ' + (a.days.length === 7 ? 'Every day' : a.days.map(d => d.slice(0,3)).join(', ') || 'Choose days');
  }
});
document.addEventListener('click', async event => {
  const el = event.target.closest('[data-settings-action]');
  if (!el || !workSetup || workSetup.saving) return;
  try {
    const action = el.dataset.settingsAction;
    if (action === 'add' || action === 'edit') openSettingsEditor(el.dataset.kind, el.dataset.key);
    if (action === 'cancel') { workSetup.editor = null; workSetup.error = ''; }
    if (action === 'next') { validateSettingsDetails(workSetup.editor); workSetup.editor.step = 2; workSetup.error = ''; }
    if (action === 'back') { workSetup.editor.step = 1; workSetup.error = ''; }
    if (action === 'days') {
      workSetup.editor.linksOpen = true;
      const option = settingsOptions(workSetup.editor)[Number(el.dataset.option)];
      const a = workSetup.editor.data.assignments.find(a => sameSettingLink(a, option));
      a.days = el.dataset.preset === 'Weekdays' ? WEEK_DAYS.slice(0,5) : el.dataset.preset === 'Weekend' ? WEEK_DAYS.slice(5) : [...WEEK_DAYS];
    }
    if (action === 'close') { const returnTab = workSetup.returnTab || (isAdmin ? 'master' : 'settings'); workSetup = null; state.tab = returnTab; if (returnTab === 'settings') state.settingsBranch = 'work'; }
    if (action === 'save') { await saveSettingsEditor(); return; }
    render();
    if (['edit','add','next','back'].includes(action)) document.querySelector('.ws-editor')?.scrollIntoView({block: 'start'});
  } catch (error) {
    if (workSetup) { workSetup.saving = false; workSetup.error = error.message; if(workSetup.editor) workSetup.editor.linksOpen = true; render(); document.querySelector('#settings-error')?.scrollIntoView({block:'nearest'}); }
    else toast(error.message);
  }
});
window.addEventListener('beforeunload', event => { if (workSetup?.editor) { event.preventDefault(); event.returnValue = ''; } });

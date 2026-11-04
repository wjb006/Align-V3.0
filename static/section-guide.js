/* Guided section setup and event entry. Loaded once, after app.js. */
var guideScreen = null;
var GUIDE_ICONS = ['📅', '🏥', '🦷', '💊', '🏠', '💼', '✈️', '🎂', '🛒', '•'];
var GUIDE_COLOURS = ['#0878F9', '#16D9F2', '#22D6C4', '#365CE6', '#7C5CFF', '#F5A524', '#FF7798', '#8AF3D1'];
var GUIDE_TYPES = ['Event', 'Appointment', 'Meeting', 'Task', 'Other'];
var SECTION_GUIDE_STEPS = ['Name and colour', 'Calendar', 'Saved places', 'Travel and alerts'];
var EVENT_GUIDE_STEPS = ['Type', 'Details', 'Label', 'Notes', 'Name and where'];

function guideCalendars() {
  const seen = new Map();
  for (const calendar of [...(state.boot?.icloud_event_calendars || []), ...(state.boot?.icloud_public?.calendars || [])]) {
    if (calendar && calendar.id && !seen.has(calendar.id)) seen.set(calendar.id, calendar);
  }
  return [...seen.values()];
}

function guideOffsetOptions(selected) {
  const current = Number(selected) || 0;
  const rows = [[0, 'No alert'], ...(typeof ALERT_OFFSETS !== 'undefined' ? ALERT_OFFSETS : [[15, '15 minutes'], [30, '30 minutes'], [60, '1 hour']])];
  return rows.map(([minutes, label]) => `<option value="${minutes}" ${Number(minutes) === current ? 'selected' : ''}>${escapeHtml(minutes ? `${label} before` : label)}</option>`).join('');
}

function guideModeOptions(selected) {
  if (typeof travelOptions === 'function') return travelOptions(selected || 'transit');
  return ['transit', 'bus', 'train', 'drive'].map(mode => `<option value="${mode}" ${mode === selected ? 'selected' : ''}>${mode}</option>`).join('');
}

function blankSectionDraft() {
  return {
    name: '', description: '', icon: '📅', colour: '#0878F9', calendar_id: '',
    places: [], travel_minutes: 45, travel_mode: 'transit', travel_info: '',
    leave_alert_minutes: 60, reminder_minutes: 30,
  };
}

function draftFromSection(section) {
  const draft = blankSectionDraft();
  if (!section) return draft;
  const guide = section.guide || {};
  draft.name = section.name || '';
  draft.description = section.description || '';
  draft.icon = section.icon || '📅';
  draft.colour = String(section.colour || '#0878F9').toUpperCase();
  draft.calendar_id = section.calendar_id || '';
  draft.travel_minutes = guide.travel_minutes ?? 45;
  draft.travel_mode = guide.travel_mode || 'transit';
  draft.travel_info = guide.travel_info || '';
  draft.leave_alert_minutes = guide.leave_alert_minutes ?? 60;
  draft.reminder_minutes = guide.reminder_minutes ?? 30;
  draft.places = (section.places || []).map(place => ({
    id: place.id, name: place.name || '', location: place.location || '',
    is_default: Number(place.id) === Number(guide.place_id),
  }));
  if (draft.places.length && !draft.places.some(place => place.is_default)) draft.places[0].is_default = true;
  return draft;
}

function splitGuideNotes(notes) {
  const raw = String(notes || '');
  const info = raw.match(/\[Align travel-info\]\s*([\s\S]*?)\s*\[\/Align travel-info\]/);
  const leave = raw.match(/\[Align travel reminder: (\d{1,5}) minutes before\]/);
  const reminder = raw.match(/\[Align event reminder: (\d{1,5}) minutes before\]/);
  const journey = raw.match(/\[Align travel\][\s\S]*?\[\/Align travel\]/i);
  const steps = raw.match(/\[Align travel steps\][\s\S]*?\[\/Align travel steps\]/i);
  const text = raw
    .replace(/\[Align travel-info\][\s\S]*?\[\/Align travel-info\]/g, '')
    .replace(/\[Align travel\][\s\S]*?\[\/Align travel\]/ig, '')
    .replace(/\[Align travel steps\][\s\S]*?\[\/Align travel steps\]/ig, '')
    .replace(/\n?\[Align travel reminder: \d{1,5} minutes before\]/g, '')
    .replace(/\n?\[Align event reminder: \d{1,5} minutes before\]/g, '')
    .trim();
  const number = match => {
    const value = match ? Number(match[1]) : 0;
    return value > 0 && value <= 10080 ? value : 0;
  };
  return {info: info ? info[1].trim() : '', leave: number(leave), reminder: number(reminder), notes: text, journey: [journey?.[0], steps?.[0]].filter(Boolean).join('\n')};
}

function draftFromEvent(event, slot) {
  const section = state.sectionData || {};
  const guide = section.guide || {};
  const place = (section.places || []).find(item => Number(item.id) === Number(guide.place_id)) || null;
  const parsed = splitGuideNotes(event?.notes || '');
  const start = event?.start_at || slot?.start_at || `${isoToday()}T09:00`;
  const end = event?.end_at || slot?.end_at || `${isoToday()}T10:00`;
  return {
    event_type: event?.event_type || 'Appointment',
    custom_type: '',
    calendar_id: section.calendar_id || '',
    date: String(start).slice(0, 10),
    start_time: event?.all_day ? '09:00' : String(start).slice(11, 16) || '09:00',
    end_time: event?.all_day ? '10:00' : String(end).slice(11, 16) || '10:00',
    all_day: !!event?.all_day,
    location: event?.location || place?.location || '',
    place_name: place?.name || '',
    save_place: false,
    travel_minutes: guide.travel_minutes ?? 45,
    travel_mode: guide.travel_mode || (typeof personalPrefs === 'function' ? personalPrefs().default_travel : '') || 'transit',
    travel_info: event ? parsed.info : (guide.travel_info || ''),
    leave_alert_minutes: event ? parsed.leave : (guide.leave_alert_minutes ?? 60),
    reminder_minutes: event ? parsed.reminder : (guide.reminder_minutes ?? 30),
    label_name: event?.label_name || '',
    new_label: '',
    notes: parsed.notes,
    journey: parsed.journey,
    title: event?.title || '',
    lookup_travel: !event,
  };
}

function openSectionGuide(sectionId) {
  const existing = sectionId ? (state.boot?.sections || []).find(section => Number(section.id) === Number(sectionId)) : null;
  guideScreen = {
    kind: 'section', step: 1, saving: false, error: '', id: existing?.id || sectionId || '',
    draft: draftFromSection(existing), catalog: {places: [], labels: []},
    placeDraft: {kind: '', name: '', location: ''}, calendarName: '',
  };
  state.tab = 'section-guide';
  render();
  if (sectionId) {
    void api(`/api/sections/${sectionId}`).then(section => {
      if (!guideScreen || guideScreen.kind !== 'section' || String(guideScreen.id) !== String(sectionId)) return;
      guideScreen.draft = draftFromSection(section);
      guideScreen.error = '';
      render();
    }).catch(error => {
      if (!guideScreen) return;
      guideScreen.error = error.message;
      render();
    });
  }
  void loadGuideCatalog();
}

function openEventGuide(sectionId, eventId, slot) {
  const id = sectionId || state.sectionId;
  const start = (event) => {
    guideScreen = {
      kind: 'event', step: 1, saving: false, error: '', id: event?.id || '',
      draft: draftFromEvent(event, slot), catalog: {places: state.sectionData?.places || [], labels: state.sectionData?.labels || []},
      placeDraft: {kind: '', name: '', location: ''}, calendarName: '',
    };
    state.tab = 'event-guide';
    render();
    void loadGuideCatalog();
  };
  if (eventId) {
    const event = state.sectionData?.events?.find(item => item.source_kind === 'align' && Number(item.id) === Number(eventId));
    if (!event) { toast('Open the section, then edit the event from there.'); return; }
    start(event);
    return;
  }
  if (!state.sectionData || Number(state.sectionId) !== Number(id)) {
    void openSection(id).then(() => start(null)).catch(error => toast(error.message));
    return;
  }
  start(null);
}

async function loadGuideCatalog() {
  try {
    const catalog = await api('/api/section-guide');
    if (!guideScreen) return;
    guideScreen.catalog = {places: catalog.places || [], labels: catalog.labels || []};
    const typing = document.activeElement?.closest?.('.guide-page input, .guide-page textarea, .guide-page select');
    if (!typing && (state.tab === 'section-guide' || state.tab === 'event-guide')) render();
  } catch (_) { /* The wizard still works before the catalogue loads. */ }
}

function plannerSectionsBlock() {
  const sections = state.boot?.sections || [];
  return `<section class="section planner-sections"><div class="section-head"><h2>Planner sections</h2></div><p class="subtle">Set up a section such as Appointments. New events can reuse its calendar, places, travel time and alerts.</p><div class="button-row"><button type="button" class="primary-button" data-action="new-section">New section</button></div><div class="quick-grid">${sections.map(section => `<button type="button" class="quick-action" data-action="open-section" data-id="${section.id}" style="border-left:4px solid ${escapeHtml(section.colour || '#0878F9')}"><b>${escapeHtml(section.icon || '•')}</b>${escapeHtml(section.name)}<small>${escapeHtml(section.calendar_name || 'Saved in Align')}</small></button>`).join('') || '<p class="helper">No planner sections yet. An Appointments section is a good place to start.</p>'}</div></section>`;
}

function guideField(id, label, control) {
  return `<label class="field" for="${id}"><span>${label}</span>${control}</label>`;
}

function renderGuideShell(title, eyebrow, steps, inner) {
  const step = guideScreen.step;
  return `<section class="page guide-page"><button type="button" class="text-button" data-guide-action="cancel">‹ Back</button><p class="eyebrow">${escapeHtml(eyebrow)}</p><h1>${escapeHtml(title)}</h1><p class="guide-progress">Step ${step} of ${steps.length} · ${escapeHtml(steps[step - 1])}</p><div class="guide-meter" aria-hidden="true"><span style="width:${Math.round(step / steps.length * 100)}%"></span></div><ol class="guide-step-list">${steps.map((label, index) => `<li class="${index + 1 === step ? 'current' : index + 1 < step ? 'done' : ''}">${escapeHtml(label)}</li>`).join('')}</ol><p class="form-error" role="alert" ${guideScreen.error ? '' : 'hidden'}>${escapeHtml(guideScreen.error || '')}</p><section class="card guide-card">${inner}</section><div class="guide-nav">${step > 1 ? `<button type="button" class="secondary-button" data-guide-action="back" ${guideScreen.saving ? 'disabled' : ''}>Back</button>` : `<button type="button" class="secondary-button" data-guide-action="cancel">Cancel</button>`}<button type="button" class="primary-button" data-guide-action="${step === steps.length ? 'save' : 'next'}" ${guideScreen.saving ? 'disabled' : ''}>${guideScreen.saving ? 'Saving…' : step === steps.length ? 'Save' : 'Continue'}</button></div></section>`;
}

function renderSectionStep() {
  const draft = guideScreen.draft;
  if (guideScreen.step === 1) {
    return `<h2>What should this section be called?</h2><p class="helper">For example, Appointments. You can change the name later.</p>${guideField('guide-name', 'Section name', `<input id="guide-name" data-guide-field="name" required maxlength="80" value="${escapeHtml(draft.name)}" placeholder="Appointments" autocomplete="off">`)}<p class="field-label">Icon</p><div class="guide-chips" role="listbox" aria-label="Section icon">${GUIDE_ICONS.map(icon => `<button type="button" class="guide-chip ${draft.icon === icon ? 'selected' : ''}" data-guide-action="pick-icon" data-value="${escapeHtml(icon)}" aria-pressed="${draft.icon === icon}">${escapeHtml(icon)}</button>`).join('')}</div>${guideField('guide-icon', 'Or type an icon', `<input id="guide-icon" data-guide-field="icon" maxlength="4" value="${escapeHtml(draft.icon)}">`)}<p class="field-label">Colour</p><div class="guide-chips" role="listbox" aria-label="Section colour">${GUIDE_COLOURS.map(colour => `<button type="button" class="guide-swatch ${draft.colour.toUpperCase() === colour ? 'selected' : ''}" style="--swatch:${colour}" data-guide-action="pick-colour" data-value="${colour}" aria-label="${colour}" aria-pressed="${draft.colour.toUpperCase() === colour}"></button>`).join('')}</div>${guideField('guide-description', 'Short description (optional)', `<input id="guide-description" data-guide-field="description" maxlength="180" value="${escapeHtml(draft.description)}" placeholder="GP visits, hospitals and check-ups">`)}`;
  }
  if (guideScreen.step === 2) {
    const calendars = guideCalendars();
    const connected = !!state.boot?.icloud_public?.connected;
    return `<h2>Which calendar should this use?</h2><p class="helper">Pick one you already have, or create a new calendar. You can also keep the section in Align only.</p>${guideField('guide-calendar', 'Calendar', `<select id="guide-calendar" data-guide-field="calendar_id"><option value="">Keep this in Align only</option>${calendars.map(calendar => `<option value="${escapeHtml(calendar.id)}" ${calendar.id === draft.calendar_id ? 'selected' : ''}>${escapeHtml(calendar.name)}</option>`).join('')}</select>`)}${connected ? `${guideField('guide-new-calendar', 'Or create a new calendar', `<input id="guide-new-calendar" data-guide-calendar-name maxlength="80" value="${escapeHtml(guideScreen.calendarName)}" placeholder="Appointments">`)}<p class="helper">Continue creates that calendar and selects it for this section.</p>` : '<p class="helper">Connect iCloud in Settings → Events & calendars when you want this section to use an iPhone calendar. Until then, events stay in Align.</p>'}`;
  }
  if (guideScreen.step === 3) {
    const adding = guideScreen.placeDraft.kind;
    const list = draft.places.map((place, index) => `<article class="guide-place"><label class="setup-check"><input type="radio" name="guide-default-place" data-guide-action="default-place" data-index="${index}" ${place.is_default ? 'checked' : ''}><span>${escapeHtml(place.name || place.location)} ${place.is_default ? '· default' : ''}</span></label><p class="helper">${place.name ? escapeHtml(place.location) : 'Location only'}</p><button type="button" class="small-button" data-guide-action="remove-place" data-index="${index}">Remove</button></article>`).join('');
    const form = adding === 'named'
      ? `${guideField('guide-place-name', 'Place name', `<input id="guide-place-name" data-guide-draft="name" maxlength="80" value="${escapeHtml(guideScreen.placeDraft.name)}" placeholder="GP">`)}${guideField('guide-place-location', 'Location', `<input id="guide-place-location" data-guide-draft="location" maxlength="240" value="${escapeHtml(guideScreen.placeDraft.location)}" placeholder="Surgery address">`)}`
      : adding === 'location'
        ? `<p class="helper">A hospital can be saved with its location only.</p>${guideField('guide-place-location', 'Location', `<input id="guide-place-location" data-guide-draft="location" maxlength="240" value="${escapeHtml(guideScreen.placeDraft.location)}" placeholder="Royal Hospital">`)}`
        : '';
    return `<h2>Save the places you go back to</h2><p class="helper">Add a GP with a name and a location, or a hospital with just the location. Mark one as the usual place for new events.</p>${list || '<p class="helper">No places yet. You can add them now or when you create an event.</p>'}${adding ? form + '<div class="button-row"><button type="button" class="secondary-button" data-guide-action="add-place">Add this place</button><button type="button" class="text-button" data-guide-action="place-kind" data-value="">Cancel</button></div>' : `<div class="guide-types"><button type="button" class="guide-choice" data-guide-action="place-kind" data-value="named"><strong>Named place</strong><span>A GP, with a name and a location.</span></button><button type="button" class="guide-choice" data-guide-action="place-kind" data-value="location"><strong>Location only</strong><span>A hospital, saved by where it is.</span></button></div>`}`;
  }
  return `<h2>Travel time and alerts</h2><p class="helper">New events in this section start with these choices. You can change them on each event.</p><div class="guide-two">${guideField('guide-travel-minutes', 'Usual travel time (minutes)', `<input id="guide-travel-minutes" data-guide-field="travel_minutes" type="number" min="0" max="10080" inputmode="numeric" value="${escapeHtml(draft.travel_minutes)}">`)}${guideField('guide-travel-mode', 'Usual way of travelling', `<select id="guide-travel-mode" data-guide-field="travel_mode">${guideModeOptions(draft.travel_mode)}</select>`)}</div>${guideField('guide-travel-info', 'Travel note', `<textarea id="guide-travel-info" data-guide-field="travel_info" maxlength="500" rows="3" placeholder="Bus from home, or allow time to park">${escapeHtml(draft.travel_info)}</textarea>`)}${guideField('guide-leave-alert', 'Leave-by travel alert', `<select id="guide-leave-alert" data-guide-field="leave_alert_minutes">${guideOffsetOptions(draft.leave_alert_minutes)}</select>`)}<p class="helper">This is the same fixed leave reminder Align already puts on timed events. Your calendar app delivers it.</p>${guideField('guide-reminder', 'Reminder before the event', `<select id="guide-reminder" data-guide-field="reminder_minutes">${guideOffsetOptions(draft.reminder_minutes)}</select>`)}${guideScreen.id ? `<button type="button" class="danger-button" data-action="delete-section" data-id="${guideScreen.id}">Delete section</button>` : ''}`;
}

function renderEventStep() {
  const draft = guideScreen.draft;
  const section = state.sectionData || {};
  if (guideScreen.step === 1) {
    return `<h2>What are you adding?</h2><p class="helper">The rest of this ${escapeHtml(section.name || 'section')} event starts from the section defaults. Everything stays editable.</p><div class="guide-types">${GUIDE_TYPES.map(type => `<button type="button" class="guide-choice ${draft.event_type === type ? 'selected' : ''}" data-guide-action="pick-type" data-value="${escapeHtml(type)}" aria-pressed="${draft.event_type === type}"><strong>${escapeHtml(type)}</strong><span>${type === 'Other' ? 'Type your own name on the next step.' : `Saved as ${escapeHtml(type)}.`}</span></button>`).join('')}</div>${draft.event_type === 'Other' ? guideField('guide-custom-type', 'Custom type', `<input id="guide-custom-type" data-guide-field="custom_type" maxlength="40" value="${escapeHtml(draft.custom_type)}" placeholder="Check-up">`) : ''}`;
  }
  if (guideScreen.step === 2) {
    const calendars = guideCalendars();
    return `<h2>Details from ${escapeHtml(section.name || 'this section')}</h2><p class="helper">Calendar, place, travel time and alerts are filled in from the section. Change anything that is different this time.</p>${guideField('guide-event-date', 'Date', `<input id="guide-event-date" data-guide-field="date" type="date" required value="${escapeHtml(draft.date)}">`)}<label class="setup-check"><input data-guide-field="all_day" type="checkbox" ${draft.all_day ? 'checked' : ''}> All-day event</label>${draft.all_day ? '' : `<div class="guide-two">${guideField('guide-start', 'Start', `<input id="guide-start" data-guide-field="start_time" type="time" required value="${escapeHtml(draft.start_time)}">`)}${guideField('guide-end', 'End', `<input id="guide-end" data-guide-field="end_time" type="time" required value="${escapeHtml(draft.end_time)}">`)}</div>`}${guideField('guide-event-calendar', 'Calendar', `<select id="guide-event-calendar" data-guide-field="calendar_id"><option value="">Align only</option>${calendars.map(calendar => `<option value="${escapeHtml(calendar.id)}" ${calendar.id === draft.calendar_id ? 'selected' : ''}>${escapeHtml(calendar.name)}</option>`).join('')}</select>`)}${guideField('guide-event-place', 'Place', `<input id="guide-event-place" data-guide-field="location" maxlength="240" value="${escapeHtml(draft.location)}" placeholder="Default place, or type another" autocomplete="off">`)}<div class="guide-suggest" data-guide-suggestions></div><div class="guide-two">${guideField('guide-event-travel', 'Travel time (minutes)', `<input id="guide-event-travel" data-guide-field="travel_minutes" type="number" min="0" max="10080" inputmode="numeric" value="${escapeHtml(draft.travel_minutes)}">`)}${guideField('guide-event-mode', 'Travel method', `<select id="guide-event-mode" data-guide-field="travel_mode">${guideModeOptions(draft.travel_mode)}</select>`)}</div>${guideField('guide-event-travel-info', 'Travel note', `<textarea id="guide-event-travel-info" data-guide-field="travel_info" maxlength="500" rows="3">${escapeHtml(draft.travel_info)}</textarea>`)}${draft.all_day ? '' : guideField('guide-event-leave', 'Leave-by travel alert', `<select id="guide-event-leave" data-guide-field="leave_alert_minutes">${guideOffsetOptions(draft.leave_alert_minutes)}</select>`)}${guideField('guide-event-reminder', 'Reminder before the event', `<select id="guide-event-reminder" data-guide-field="reminder_minutes">${guideOffsetOptions(draft.reminder_minutes)}</select>`)}<label class="setup-check"><input data-guide-field="lookup_travel" type="checkbox" ${draft.lookup_travel ? 'checked' : ''}> Look up a journey when I save</label>`;
  }
  if (guideScreen.step === 3) {
    const labels = guideScreen.catalog?.labels || section.labels || [];
    return `<h2>Choose a label</h2><p class="helper">Pick one you have used, or type a new label. You can leave this blank.</p><div class="guide-chips">${labels.map(label => `<button type="button" class="guide-chip ${draft.label_name === label.name ? 'selected' : ''}" data-guide-action="pick-label" data-value="${escapeHtml(label.name)}" aria-pressed="${draft.label_name === label.name}">${escapeHtml(label.name)}</button>`).join('') || '<p class="helper">No labels yet.</p>'}</div>${guideField('guide-new-label', 'Or create a label', `<input id="guide-new-label" data-guide-field="new_label" maxlength="40" value="${escapeHtml(draft.new_label)}" placeholder="Health">`)}`;
  }
  if (guideScreen.step === 4) {
    return `<h2>Notes</h2><p class="helper">Anything you want to remember. Travel details are saved with the event as well.</p>${guideField('guide-notes', 'Notes', `<textarea id="guide-notes" data-guide-field="notes" maxlength="2000" rows="6" placeholder="Bring your letters">${escapeHtml(draft.notes)}</textarea>`)}`;
  }
  const typeName = draft.event_type === 'Other' ? (draft.custom_type || 'Other') : draft.event_type;
  const calendar = guideCalendars().find(item => item.id === draft.calendar_id);
  return `<h2>Name and where</h2><p class="helper">Start typing a saved place to reuse it. You can also save this location for next time.</p>${guideField('guide-title', 'Name', `<input id="guide-title" data-guide-field="title" required maxlength="160" value="${escapeHtml(draft.title)}" placeholder="Dentist">`)}${guideField('guide-where', 'Where', `<input id="guide-where" data-guide-field="location" maxlength="240" data-address-search="true" data-address-target="guide-where" value="${escapeHtml(draft.location)}" placeholder="Start typing a saved place or address" autocomplete="off">`)}<div class="address-results" id="guide-where-results" data-address-results="guide-where" role="listbox" aria-label="Address suggestions"></div><div class="guide-suggest" data-guide-suggestions role="listbox" aria-label="Saved places"></div><label class="setup-check"><input data-guide-field="save_place" type="checkbox" ${draft.save_place ? 'checked' : ''}> Save this place for next time</label>${draft.save_place ? guideField('guide-place-save-name', 'Name on the saved places list', `<input id="guide-place-save-name" data-guide-field="place_name" maxlength="80" value="${escapeHtml(draft.place_name)}" placeholder="GP or hospital">`) : ''}<aside class="guide-summary"><p><strong>${escapeHtml(typeName)}</strong> in ${escapeHtml(section.name || 'this section')}</p><p>${escapeHtml(calendar?.name || 'Align only')} · ${escapeHtml(draft.location || 'No place yet')}</p><p>${draft.all_day ? 'All day' : `${escapeHtml(draft.date)} · ${escapeHtml(draft.start_time)}–${escapeHtml(draft.end_time)}`}</p><p>Travel ${escapeHtml(String(draft.travel_minutes || 0))} min · leave alert ${escapeHtml(String(draft.leave_alert_minutes || 0))} min · reminder ${escapeHtml(String(draft.reminder_minutes || 0))} min</p></aside>${guideScreen.id ? `<button type="button" class="danger-button" data-action="delete-section-event" data-id="${guideScreen.id}">Delete event</button>` : ''}`;
}

function renderSectionGuide() {
  if (!guideScreen || guideScreen.kind !== 'section') {
    return '<section class="page guide-page"><h1>New section</h1><button type="button" class="primary-button" data-guide-action="start-section">Start section setup</button></section>';
  }
  const title = guideScreen.id ? `Edit ${guideScreen.draft.name || 'section'}` : 'New section';
  return renderGuideShell(title, 'Section setup', SECTION_GUIDE_STEPS, renderSectionStep());
}

function renderEventGuide() {
  if (!guideScreen || guideScreen.kind !== 'event') {
    return '<section class="page guide-page"><h1>New event</h1><p class="helper">Open a section, then use + Event.</p></section>';
  }
  const name = state.sectionData?.name || 'section';
  return renderGuideShell(guideScreen.id ? 'Edit event' : `Add to ${name}`, '+ Event', EVENT_GUIDE_STEPS, renderEventStep());
}

function guidePlaces() {
  const seen = new Set();
  const rows = [];
  for (const place of [...(state.sectionData?.places || []), ...(guideScreen?.draft?.places || []), ...(guideScreen?.catalog?.places || [])]) {
    const key = `${String(place.name || '').toLowerCase()}|${String(place.location || '').toLowerCase()}`;
    if (!place.location || seen.has(key)) continue;
    seen.add(key);
    rows.push(place);
  }
  return rows;
}

function refreshPlaceSuggestions() {
  const box = document.querySelector('[data-guide-suggestions]');
  if (!box || !guideScreen) return;
  const query = `${guideScreen.draft.location || ''} ${guideScreen.draft.title || ''} ${guideScreen.draft.place_name || ''}`.trim().toLowerCase();
  const matches = guidePlaces().filter(place => {
    const haystack = `${place.name || ''} ${place.location || ''}`.toLowerCase();
    return !query || haystack.includes(query);
  }).slice(0, 6);
  box.innerHTML = matches.length ? matches.map(place => `<button type="button" class="guide-suggestion" data-guide-action="use-place" data-name="${encodeURIComponent(place.name || '')}" data-location="${encodeURIComponent(place.location || '')}"><strong>${escapeHtml(place.name || place.location)}</strong>${place.name ? `<small>${escapeHtml(place.location)}</small>` : ''}</button>`).join('') : '';
}

function syncGuideControl(target) {
  if (!guideScreen || !target?.dataset) return;
  if (target.dataset.guideCalendarName !== undefined && target.hasAttribute('data-guide-calendar-name')) {
    guideScreen.calendarName = target.value;
  }
  if (target.hasAttribute('data-guide-draft')) {
    guideScreen.placeDraft[target.dataset.guideDraft] = target.value;
    return;
  }
  if (!target.hasAttribute('data-guide-field')) return;
  const key = target.dataset.guideField;
  const value = target.type === 'checkbox' ? target.checked : target.value;
  guideScreen.draft[key] = value;
  if (key === 'all_day' || key === 'save_place' || key === 'event_type') render();
  if (key === 'location' || key === 'title' || key === 'place_name') refreshPlaceSuggestions();
}

function guideFail(message) {
  guideScreen.error = message;
  render();
  document.querySelector('.form-error')?.focus?.();
}

function validateGuideStep() {
  const draft = guideScreen.draft;
  if (guideScreen.kind === 'section' && guideScreen.step === 1 && !draft.name.trim()) return 'Give this section a name.';
  if (guideScreen.kind === 'section' && guideScreen.step === 4) {
    const minutes = Number(draft.travel_minutes);
    if (!Number.isInteger(minutes) || minutes < 0 || minutes > 10080) return 'Enter a travel time between 0 minutes and 1 week.';
  }
  if (guideScreen.kind === 'event' && guideScreen.step === 1 && draft.event_type === 'Other' && !draft.custom_type.trim()) return 'Type a name for this event type.';
  if (guideScreen.kind === 'event' && guideScreen.step === 2) {
    if (!draft.date) return 'Choose a date.';
    if (!draft.all_day && (!draft.start_time || !draft.end_time || draft.end_time <= draft.start_time)) return 'The end time needs to be after the start time.';
  }
  if (guideScreen.kind === 'event' && guideScreen.step === 5 && !draft.title.trim()) return 'Give this event a name.';
  if (guideScreen.kind === 'event' && guideScreen.step === 5 && draft.save_place && !draft.location.trim()) return 'Add a location before saving the place.';
  return '';
}

async function saveSectionGuide() {
  const draft = guideScreen.draft;
  if (guideScreen.calendarName.trim()) await ensureGuideCalendar();
  const body = {
    name: draft.name.trim(), description: draft.description.trim(), icon: (draft.icon || '📅').trim() || '📅',
    colour: draft.colour, calendar_id: draft.calendar_id || '', import_enabled: true, export_enabled: !!draft.calendar_id,
    sort_order: 100, parent_branch_id: null, active: true,
    guide: {
      travel_minutes: Number(draft.travel_minutes), travel_mode: draft.travel_mode, travel_info: draft.travel_info,
      leave_alert_minutes: Number(draft.leave_alert_minutes), reminder_minutes: Number(draft.reminder_minutes),
      places: draft.places.map(place => ({id: place.id, name: place.name, location: place.location, is_default: !!place.is_default})),
    },
  };
  const id = guideScreen.id;
  const saved = await api(id ? `/api/sections/${id}` : '/api/sections', {method: id ? 'PUT' : 'POST', body});
  guideScreen = null;
  state.sectionData = null;
  await refresh();
  await openSection(saved.id || id);
  toast(id ? 'Section updated.' : 'Section added.');
}

async function ensureGuideCalendar() {
  const name = guideScreen.calendarName.trim();
  if (!name) return;
  const result = await api('/api/icloud/create-event-calendar', {method: 'POST', body: {name}});
  state.boot.icloud_event_calendars = result.event_calendars || state.boot.icloud_event_calendars || [];
  guideScreen.draft.calendar_id = result.created_calendar.id;
  guideScreen.calendarName = '';
}

async function saveEventGuide() {
  const draft = guideScreen.draft;
  const modeLabels = {drive: 'Driving', bus: 'Bus', train: 'Train', transit: 'Bus and train'};
  const summary = [[Number(draft.travel_minutes) ? `${Number(draft.travel_minutes)} minutes` : '', modeLabels[draft.travel_mode] || ''].filter(Boolean).join(' · '), draft.travel_info.trim()].filter(Boolean).join('\n');
  let notes = [draft.notes.trim(), draft.journey].filter(Boolean).join('\n');
  let travelWarning = '';
  if (draft.lookup_travel && !draft.all_day && draft.location.trim()) {
    try {
      const prefs = typeof personalPrefs === 'function' ? personalPrefs() : {};
      const journey = await api('/api/personal/journey', {method: 'POST', body: {
        destination: draft.location.trim(), arrival: `${draft.date}T${draft.start_time}`,
        mode: draft.travel_mode || prefs.default_travel || 'transit',
        departure_buffer: Number(prefs.departure_buffer ?? 5), arrival_buffer: Number(prefs.arrival_buffer ?? 10),
      }});
      const plan = journey.journeys?.[0];
      if (plan?.notes) notes = `${notes}\n[Align travel]\n${plan.notes}\n[/Align travel]${plan.steps?.length ? `\n[Align travel steps]\n${JSON.stringify(plan.steps)}\n[/Align travel steps]` : ''}`.trim();
    } catch (error) {
      travelWarning = ` Saved without a live journey: ${error.message}`;
    }
  }
  const body = {
    title: draft.title.trim(), location: draft.location.trim(), calendar_id: draft.calendar_id || '', all_day: !!draft.all_day,
    notes, travel_info: summary, leave_alert_minutes: draft.all_day ? 0 : Number(draft.leave_alert_minutes || 0),
    reminder_minutes: Number(draft.reminder_minutes || 0),
    event_type: draft.event_type === 'Other' ? draft.custom_type.trim() : draft.event_type,
    label_name: (draft.new_label || draft.label_name || '').trim(),
    save_place: !!draft.save_place, place_name: (draft.place_name || draft.title).trim(),
    show_post_travel: false, post_travel_mode: draft.travel_mode || 'transit',
  };
  if (draft.all_day) body.date = draft.date;
  else { body.start_at = `${draft.date}T${draft.start_time}`; body.end_at = `${draft.date}T${draft.end_time}`; }
  const id = guideScreen.id;
  if (!id) body.request_id = crypto.randomUUID ? crypto.randomUUID() : `guide-${Date.now()}`;
  const saved = await api(id ? `/api/organiser-events/${id}` : `/api/sections/${state.sectionId}/events`, {method: id ? 'PUT' : 'POST', body});
  const sectionId = saved.section_id || state.sectionId;
  guideScreen = null;
  state.sectionData = null;
  await refresh();
  await openSection(sectionId);
  toast((id ? 'Event updated.' : 'Event added.') + travelWarning);
}

document.addEventListener('input', event => { syncGuideControl(event.target); });
document.addEventListener('change', event => { syncGuideControl(event.target); });
document.addEventListener('click', async event => {
  const button = event.target.closest?.('[data-guide-action]');
  if (!button) return;
  const action = button.dataset.guideAction;
  try {
    if (action === 'start-section') { openSectionGuide(); return; }
    if (!guideScreen) return;
    if (action === 'cancel') {
      const backTo = guideScreen.kind === 'event' && state.sectionId ? 'section' : 'sections';
      guideScreen = null;
      state.tab = backTo;
      render();
      return;
    }
    if (action === 'back') { guideScreen.error = ''; guideScreen.step = Math.max(1, guideScreen.step - 1); render(); return; }
    if (action === 'pick-icon') { guideScreen.draft.icon = button.dataset.value; render(); return; }
    if (action === 'pick-colour') { guideScreen.draft.colour = button.dataset.value; render(); return; }
    if (action === 'pick-type') { guideScreen.draft.event_type = button.dataset.value; render(); return; }
    if (action === 'pick-label') { guideScreen.draft.label_name = button.dataset.value; guideScreen.draft.new_label = ''; render(); return; }
    if (action === 'place-kind') { guideScreen.placeDraft = {kind: button.dataset.value || '', name: '', location: ''}; render(); return; }
    if (action === 'default-place') {
      const index = Number(button.dataset.index);
      guideScreen.draft.places.forEach((place, placeIndex) => { place.is_default = placeIndex === index; });
      render();
      return;
    }
    if (action === 'remove-place') {
      guideScreen.draft.places.splice(Number(button.dataset.index), 1);
      if (guideScreen.draft.places.length && !guideScreen.draft.places.some(place => place.is_default)) guideScreen.draft.places[0].is_default = true;
      render();
      return;
    }
    if (action === 'add-place') {
      const location = guideScreen.placeDraft.location.trim();
      if (!location) { guideFail('Add a location for this place.'); return; }
      if (guideScreen.placeDraft.kind === 'named' && !guideScreen.placeDraft.name.trim()) { guideFail('Add a name, such as GP.'); return; }
      guideScreen.draft.places.push({name: guideScreen.placeDraft.kind === 'named' ? guideScreen.placeDraft.name.trim() : '', location, is_default: !guideScreen.draft.places.length});
      guideScreen.placeDraft = {kind: '', name: '', location: ''};
      guideScreen.error = '';
      render();
      return;
    }
    if (action === 'use-place') {
      const name = decodeURIComponent(button.dataset.name || '');
      const location = decodeURIComponent(button.dataset.location || '');
      guideScreen.draft.location = location;
      if (!guideScreen.draft.title.trim() && name) guideScreen.draft.title = name;
      if (!guideScreen.draft.place_name.trim() && name) guideScreen.draft.place_name = name;
      render();
      return;
    }
    if (action === 'next' || action === 'save') {
      const problem = validateGuideStep();
      if (problem) { guideFail(problem); return; }
      guideScreen.error = '';
      if (action === 'next') {
        if (guideScreen.kind === 'section' && guideScreen.step === 2 && guideScreen.calendarName.trim()) {
          guideScreen.saving = true; render();
          await ensureGuideCalendar();
          guideScreen.saving = false;
        }
        guideScreen.step += 1;
        render();
        if (guideScreen.kind === 'event' && guideScreen.step === 5) refreshPlaceSuggestions();
        return;
      }
      guideScreen.saving = true; render();
      if (guideScreen.kind === 'section') await saveSectionGuide();
      else await saveEventGuide();
    }
  } catch (error) {
    if (guideScreen) { guideScreen.saving = false; guideFail(error.message || 'Something went wrong.'); }
    else toast(error.message);
  }
});

document.addEventListener('focusin', event => {
  if (event.target?.id === 'guide-where' || event.target?.id === 'guide-event-place' || event.target?.id === 'guide-title') refreshPlaceSuggestions();
});

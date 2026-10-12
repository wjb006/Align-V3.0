const state = {
  tab: new URLSearchParams(location.search).has('studio') ? 'assets' : 'today',
  boot: null,
  masterTab: 'setup',
  settingsBranch: 'profile',
  scheduleStart: isoToday(),
  scheduleEnd: isoOffset(42),
  sectionId: null,
  sectionData: null,
  sectionDefinitions: [],
};
window.ALIGN_STATE = state;

const isAdmin = window.ALIGN_ADMIN === true;
let adminToken = isAdmin ? sessionStorage.getItem('align-admin-token') || '' : '';
const app = document.querySelector('#app');
const modalRoot = document.querySelector('#modal-root');
const toastElement = document.querySelector('#toast');
const WEEK_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const BUILD_VERSION = 156;
const ASSET_VERSION = `${BUILD_VERSION}-v45`;
const ALERT_OFFSETS = [
  [5, '5 minutes'], [10, '10 minutes'], [15, '15 minutes'], [30, '30 minutes'], [45, '45 minutes'],
  [60, '1 hour'], [120, '2 hours'], [1440, '1 day'], [2880, '2 days'], [7200, '5 days'], [10080, '1 week'],
];
function alertOffsetOptions(selected) {
  const value = Number(selected);
  const options = [...ALERT_OFFSETS];
  if (Number.isInteger(value) && value >= 0 && !options.some(([minutes]) => minutes === value)) {
    options.push([value, travel_reminders_label(value)]);
    options.sort((a, b) => a[0] - b[0]);
  }
  return options.map(([minutes, label]) => `<option value="${minutes}" ${minutes === value ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('');
}
function travel_reminders_label(minutes) {
  if (!minutes) return 'At start';
  const known = ALERT_OFFSETS.find(([value]) => value === minutes);
  if (known) return known[1];
  if (minutes % 1440 === 0) { const days = minutes / 1440; return `${days} day${days === 1 ? '' : 's'}`; }
  if (minutes % 60 === 0) { const hours = minutes / 60; return `${hours} hour${hours === 1 ? '' : 's'}`; }
  return `${minutes} minutes`;
}
function renderTransport() { return renderTravel150(); }
const offlineRuntime = { preparing: false, ready: false, diagnostics: null, registration: null, registrationError: '', registrationState: '', reloadingForControl: false };

function isoToday() { return toIso(new Date()); }
function isoOffset(days) { const value = new Date(); value.setDate(value.getDate() + days); return toIso(value); }
function toIso(value) {
  const local = new Date(value.getFullYear(), value.getMonth(), value.getDate(), 12);
  return `${local.getFullYear()}-${String(local.getMonth() + 1).padStart(2, '0')}-${String(local.getDate()).padStart(2, '0')}`;
}
function fromIso(value) { return new Date(`${value}T12:00:00`); }
function monday(value = new Date()) { const day = value.getDay() || 7; value = new Date(value); value.setDate(value.getDate() - day + 1); return value; }
function escapeHtml(value = '') { return String(value).replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char])); }
function prettyDate(value) { return formatDisplayDate(value); }
function weekday(value) { return fromIso(value).toLocaleDateString('en-GB', { weekday: 'short' }); }
function weekdayName(value) { return fromIso(value).toLocaleDateString('en-GB', { weekday: 'long' }); }
function dayHeading(value) {
  const day = String(value).slice(0, 10);
  const date = fromIso(day);
  return `${date.toLocaleDateString('en-GB', { weekday: 'long' })} ${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`;
}
function fullDateLabel(value) {
  return fromIso(String(value).slice(0, 10)).toLocaleDateString('en-GB', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });
}
function number(value) { return Number(value || 0).toLocaleString('en-GB', { maximumFractionDigits: 2 }); }
function hours(value) { return `${number(value)}h`; }
function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}
function currentTemplate() { return null; }
function currentLocation() { return null; }

function setConnectionStatus(mode, pending = 0) {
  const element = document.querySelector('#connection-status');
  if (!element || isAdmin) return;
  element.hidden = false;
  element.dataset.mode = mode;
  const suffix = pending ? ` · ${pending} to sync` : '';
  if (mode === 'offline') element.textContent = `Offline${suffix}`;
  else if (mode === 'caching') element.textContent = 'Caching…';
  else if (mode === 'ready') element.textContent = `Offline Ready${suffix}`;
  else if (mode === 'warning') element.textContent = `Offline setup issue${suffix}`;
  else element.textContent = pending ? `${pending} to sync` : 'Online';
}

async function rawApi(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(adminToken ? { 'X-Align-Admin': adminToken } : {}), ...(options.headers || {}) },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const payload = await response.json().catch(() => ({}));
  if (payload && typeof payload === 'object') {
    Object.defineProperty(payload, '__alignFromOfflineCache', { value: response.headers.get('X-Align-Offline-Cache') === '1', enumerable: false });
  }
  if (!response.ok) {
    const authPage = location.pathname.startsWith('/beta-') || ['/login','/invite','/forgot','/reset','/terms','/welcome','/account'].includes(location.pathname);
    if (response.status === 401 && payload.code === 'beta_login' && !authPage) { location.href='/login'; throw new Error('Sign-in required.'); }
    if (response.status === 403 && payload.code === 'terms_required' && !authPage) { location.href='/terms'; throw new Error('Terms acceptance required.'); }
    const error = new Error(payload.error || 'Something went wrong.'); error.serverResponse = true; throw error;
  }
  return payload;
}

async function api(path, options = {}) {
  const method = String(options.method || 'GET').toUpperCase();
  if (state.boot && state.boot.build_version !== BUILD_VERSION && method !== 'GET' && path !== '/api/admin/login') {
    throw new Error('The app and server versions differ. Refresh Align while connected to finish the update.');
  }

  try {
    const payload = await rawApi(path, options);
    if (!isAdmin && method === 'GET' && typeof AlignOffline !== 'undefined') {
      const remembered = await AlignOffline.remember(path, payload);
      const pending = await AlignOffline.pendingCount();
      if (payload.__alignFromOfflineCache) setConnectionStatus('offline', pending);
      else setConnectionStatus(offlineRuntime.ready ? 'ready' : 'online', pending);
      return remembered;
    }
    return payload;
  } catch (error) {
    if (isAdmin || typeof AlignOffline === 'undefined' || error.serverResponse) throw error;

    if (method === 'GET') {
      const cached = await AlignOffline.cached(path);
      if (cached !== null) {
        setConnectionStatus('offline', await AlignOffline.pendingCount());
        return cached;
      }
      throw new Error('Align cannot reach your PC and this screen has not been saved on this phone yet. Reconnect once, open it, then it will be available offline.');
    }

    if (method === 'POST' && /^\/api\/sections\/\d+\/events$/.test(path)) {
      await AlignOffline.queueOrganiserEvent(path, options.body);
      setConnectionStatus('offline', await AlignOffline.pendingCount());
      return { offline: true, queued: true };
    }

    throw new Error('This change needs a connection to your Align PC for now. Your saved offline schedule is still available.');
  }
}

async function refresh() {
  state.boot = await api('/api/bootstrap');
  state.sectionDefinitions = (await api('/api/sections/definitions')).sections || [];
  if (state.sectionData) await openSection(state.sectionId);
  if(typeof travel150!=='undefined'){travel150.items=null;travel150.result=null;}
  render();
  if(state.boot.personal?.travel_pending)void refreshRelatedTravel();
}

function toast(message, tone = '') {
  toastElement.textContent = message;
  toastElement.dataset.tone = tone || '';
  toastElement.classList.add('show');
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => toastElement.classList.remove('show'), 4200);
}

function showFormError(form, message) {
  if (!form) return;
  let note = form.querySelector('[data-form-error]');
  if (!note) {
    note = document.createElement('p');
    note.className = 'form-error';
    note.dataset.formError = 'true';
    note.setAttribute('role', 'alert');
    form.prepend(note);
  }
  note.textContent = message;
}

function notificationPermission() {
  return typeof Notification !== 'undefined' ? Notification.permission : 'unsupported';
}

async function enableBrowserNotifications() {
  if (notificationPermission() === 'unsupported') throw new Error('Browser notifications are not supported here.');
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw new Error('Browser notifications were not enabled.');
  toast('Browser notifications enabled.');
}

function reminderIcon(title = '') {
  if (/\b(train|rail|tram)\b/i.test(title)) return '/journey-icons/train.png';
  if (/\bbus\b/i.test(title)) return '/journey-icons/bus.png';
  if (/\b(leave|walk|travel|arriv)/i.test(title)) return '/journey-icons/walking.png';
  return '/icon.svg';
}
async function notifyAlign(title, body, tag, url = '/', icon = '/icon.svg') {
  if (notificationPermission() !== 'granted') return;
  const registration = await navigator.serviceWorker?.getRegistration().catch(() => null);
  if (registration?.active) {
    registration.active.postMessage({ type: 'ALIGN_SHOW_NOTIFICATION', title, body, tag, url, icon });
  } else {
    new Notification(title, { body, tag, icon });
  }
}

function leaveClock(alert) {
  const match = String(alert.alert_at || '').match(/T(\d{2}:\d{2})/);
  return match ? match[1] : '';
}

function render() {
  AlignFormatting.apply(document.body,state.boot?.builder?.document?.formatting);
  applyManagementAppearance();
  renderBottomNavigation();
  if (state.tab === 'master') state.tab = 'more';
  const activeCoreTab = coreNavDestination(state.tab);
  document.querySelectorAll('[data-nav]').forEach(button => button.classList.toggle('active', button.dataset.nav === activeCoreTab));
  if (!state.boot) {
    app.innerHTML = '<div class="empty loading-state" role="status">Loading your planner…</div>';
    return;
  }
  if (state.boot.build_version !== BUILD_VERSION) {
    const serverBuild = state.boot.build_version;
    const updateHelp = serverBuild > BUILD_VERSION
      ? 'This page is using an older app version. Connect to your Align server, then refresh to load the latest app files.'
      : 'The app and server versions differ. Restart Align on your PC using your usual launcher, then refresh this page while connected.';
    app.innerHTML = `<section class="card settings-form"><h1>Align update ready</h1><p>${updateHelp}</p><p class="helper">App build: ${BUILD_VERSION}. Server build: ${escapeHtml(serverBuild)}.</p><button class="primary-button" data-action="reload-app">Check for update</button></section>`;
    return;
  }
  if (!isAdmin && !state.boot.settings.onboarding_completed) {
    app.innerHTML = renderOnboarding();
    return;
  }
  if (['planner','calendar','add','work-setup'].includes(state.tab)) state.tab = 'sections';
  const content = { today: renderHome, home: renderHome, inbox: renderInbox, sections: renderSectionsIndex, section: renderSection, more: renderMore, transport: renderTransport, assets: renderAssets150, settings: renderUserSettings, 'builder-records': builderRecordsPage, 'builder-profile': () => builderStartup(true) }[state.tab]?.() || renderHome();
  const cloudNotice = state.boot.icloud_public?.reconnect_required ? `<div class="card" role="status"><strong>iCloud needs reconnecting</strong><p>${escapeHtml(state.boot.icloud_public.message)}</p><button class="small-button" data-nav="settings">Open settings</button></div>` : '';
  app.innerHTML = cloudNotice + content;
  app.focus({ preventScroll: true });
}

function applyManagementAppearance() {
  const appearance = state.boot?.builder?.appearance;
  if (!appearance) return;
  const root = document.documentElement;
  const colors = appearance.colors || {};
  root.style.setProperty('--blue', colors.accent);
  root.style.setProperty('--canvas', colors.canvas);
  root.style.setProperty('--surface', colors.surface);
  root.style.setProperty('--ink', colors.text);
  root.style.setProperty('--management-event-accent', appearance.events?.accent || '#6577bd');
  for (const key of ['today', 'upcoming', 'annual_leave', 'section_detail']) {
    root.style.setProperty(`--management-banner-${key.replaceAll('_', '-')}`, appearance.banners?.[key] || '#365ce6');
  }
  const luminance = hex => {
    const values = hex.match(/[0-9a-f]{2}/ig)?.map(value => parseInt(value, 16) / 255) || [0.2, 0.2, 0.2];
    const linear = values.map(value => value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  };
  for (const [key, color] of Object.entries(appearance.banners || {})) {
    root.style.setProperty(`--management-banner-ink-${key.replaceAll('_', '-')}`, luminance(color) > 0.43 ? '#162147' : '#ffffff');
  }
  document.body.dataset.managementEventStyle = appearance.events?.style || 'standard';
  document.body.dataset.managementEventDensity = appearance.events?.density || 'comfortable';
  document.body.dataset.eventTime = appearance.events?.time_place || 'left';
  document.body.dataset.eventTimeSize = appearance.events?.time_size || 'large';
  document.body.dataset.managementTextScale = appearance.type?.scale || 'default';
  document.body.dataset.managementCorners = appearance.type?.corners || 'soft';
  const theme = appearance.type?.theme || 'light';
  document.body.dataset.managementTheme = theme === 'auto' ? (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : theme;
  document.body.dataset.managementFont = appearance.type?.font || 'system';
  document.body.dataset.managementHeading = appearance.type?.heading || 'bold';
  document.body.dataset.managementWeekHeadings = appearance.calendar?.week_headings || 'show';
  const cal = appearance.calendar || {};
  for (const [key, fallback] of Object.entries({month_cell:'#f1f5fd', month_weekend:'#e9eefb', month_date_band:'#dfe7fb', today_cell:'#e4ecff', list_day:'#f1f5fd', list_day_header:'#edf2ff'})) {
    root.style.setProperty(`--cal-${key.replaceAll('_', '-')}`, cal[key] || fallback);
  }
}

const CORE_NAVIGATION = [
  {id:'today', title:'Today', icon:'⌂', destination:'today', active:true},
  {id:'inbox', title:'Inbox', icon:'☑', destination:'inbox', active:true},
  {id:'sections', title:'Sections', icon:'◫', destination:'sections', active:true},
  {id:'more', title:'More', icon:'•••', destination:'more', active:true},
];

function coreNavDestination(tab = state.tab) {
  if (['today','home'].includes(tab)) return 'today';
  if (tab === 'inbox') return 'inbox';
  if (['planner','calendar','add'].includes(tab)) return 'sections';
  if (['sections','section'].includes(tab)) return 'sections';
  return 'more';
}

function renderBottomNavigation() {
  const root = document.querySelector('#bottom-navigation');
  if (!root) return;
  const configured = (state.boot?.builder?.document?.navigation || []).filter(item => !['planner','calendar','add','work-setup','layout'].includes(item.destination));
  const hasCoreNavigation = configured.some(item => ['today','inbox','sections','more'].includes(item.destination));
  const items = hasCoreNavigation ? configured : CORE_NAVIGATION;
  const active = coreNavDestination();
  root.innerHTML = items.filter(item => item.active).map(item => `<button data-nav="${escapeHtml(item.destination)}" class="nav-item ${active===item.destination?'active':''}"><span class="nav-icon">${escapeHtml(item.icon)}</span><span>${escapeHtml(item.title)}</span></button>`).join('');
  root.style.gridTemplateColumns = `repeat(${Math.max(1,root.querySelectorAll('[data-nav]').length)}, 1fr)`;
}

function homeSection(id) {
  const item = (state.boot?.builder?.document?.home_sections || []).find(section => section.id === id);
  return !item || item.visible;
}
function homeSectionTitle(id, fallback) {
  return escapeHtml((state.boot?.builder?.document?.home_sections || []).find(section => section.id === id)?.title || fallback);
}
function eventChoice(key, fallback) {
  const value = state.boot?.builder?.appearance?.events?.[key];
  return value == null || value === '' ? fallback : value;
}
function homeSectionContent(id, key, fallback = true) {
  const item = (state.boot?.builder?.document?.home_sections || []).find(section => section.id === id);
  if (!item?.content || !(key in item.content)) return fallback;
  return Boolean(item.content[key]);
}

function renderInbox() {
  const items = state.boot?.personal?.items || [];
  return `<section class="page"><div class="add-head"><p class="eyebrow">Capture first, organise later</p><h1>Inbox</h1><p class="subtle">Notes and reminders you have saved in Align, all in one place.</p><div class="button-row"><button class="primary-button" data-personal="note">＋ Note</button><button class="secondary-button" data-personal="reminder">＋ Reminder</button></div></div><section class="section"><div class="section-head"><h2>Notes & reminders</h2></div><div class="master-list">${items.map(item => `<article class="card master-item ${item.done?'inactive':''}"><span class="branch-icon">${item.kind==='note'?'✎':'◷'}</span><div class="item-content"><p class="inbox-item-text">${escapeHtml(item.title)}</p><p>${item.kind==='note'?'Note':escapeHtml(item.due_at ? formatDisplayDateTime(item.due_at) : '')}${item.done?' · Complete':''}</p></div><div class="button-row">${item.kind==='reminder'?`<button class="small-button" data-personal="${item.done?'undo':'done'}" data-id="${item.id}">${item.done?'Reopen':'Complete'}</button>`:''}<button class="small-button" data-personal="delete" data-id="${item.id}">Delete</button></div></article>`).join('') || '<div class="card empty">Nothing in your Inbox yet. Add a note or reminder when something pops into your head.</div>'}</div></section></section>`;
}

function renderSectionsIndex() {
  const sections = state.sectionDefinitions || [];
  const work = sections.find(section => section.key === 'work');
  const visible = sections.filter(section => !section.optional || section.enabled);
  return `<section class="page"><div class="add-head"><p class="eyebrow">Your data, organised your way</p><h1>Sections</h1><p class="subtle">Sections set up in Align Management Studio appear here. Your records stay private to your account.</p></div><div class="quick-grid">${visible.map(section => `<button class="quick-action organiser-section-tile" data-section-key="${escapeHtml(section.key)}" style="border-left:4px solid ${escapeHtml(section.colour)}"><b>${escapeHtml(section.icon)}</b>${escapeHtml(section.name)}<small>${escapeHtml(section.description || 'Open your saved records')}</small></button>`).join('')}${!visible.length?'<div class="card empty">No sections have been added yet.</div>':''}</div>${!work || !work.enabled ? `<section class="section"><div class="card"><h2>Work (optional)</h2><p class="subtle">${work ? 'Add the Work database to your account. It can include locations, work areas, times, or any questions configured for Align.' : 'The Work database is not available yet. When it is ready, you can add it to your account and edit your records anytime.'}</p>${work ? '<button class="secondary-button" data-action="work-opt-in">Set up Work</button>' : ''}</div></section>` : ''}</section>`;
}

function installPanel() {
  return `<aside class="card install-panel"><p class="eyebrow">On this device</p><h2>Install Align</h2><p class="subtle">Add Align to your home screen so it opens full screen and stays available offline.</p><button type="button" class="primary-button" data-action="prompt-install">Install Align</button><p class="helper">On iPhone, use Share, then Add to Home Screen. If this browser can install apps, the button starts that.</p></aside>`;
}

function renderMore() {
  return `<section class="page"><div class="add-head"><p class="eyebrow">Everything else</p><h1>More</h1><p class="subtle">Personal settings and tools.</p></div>${installPanel()}<div class="quick-grid"><button class="quick-action" data-nav="settings"><b>⚙</b>Settings<small>Your details and calendars</small></button><button class="quick-action" data-nav="transport"><b>↗</b>Travel<small>Saved places and journey planning</small></button></div></section>`;
}

function rootParentBranches() { return (state.boot?.master.parents || []).filter(branch => branch.active && !branch.parent_id); }
function childParentBranches(parentId) { return (state.boot?.master.parents || []).filter(branch => branch.active && Number(branch.parent_id) === Number(parentId)); }
function rootSections() { return (state.boot?.sections || []).filter(section => !section.parent_branch_id); }
function childSections(parentId) { return (state.boot?.sections || []).filter(section => Number(section.parent_branch_id) === Number(parentId)); }

function renderHomeGreeting(dashboard) {
  const settings = state.boot.settings;
  const title = isAdmin
    ? (settings.user_name || 'Align admin')
    : `${greeting()}${settings.user_name ? `, ${settings.user_name}` : ''}`;
  const weather = typeof homeWeatherChip === 'function' ? homeWeatherChip() : '';
  return `<div class="hero home-greeting"><div class="home-date-row"><p class="eyebrow">${escapeHtml(fullDateLabel(dashboard.today))}</p>${weather}</div><h1>${escapeHtml(title)}</h1></div>`;
}
function renderHome() {
  const { dashboard } = state.boot;
  const sections = state.boot.builder ? state.boot.sections : rootSections();
  return `<section class="page">
    ${renderHomeGreeting(dashboard)}
    ${homeSection('stats') ? `<div class="hero-stat-row home-week-stats"><div class="hero-stat"><strong>${sections.length}</strong><span>your sections</span></div><div class="hero-stat"><strong>${dashboard.upcoming_events?.length || 0}</strong><span>upcoming events</span></div></div>` : ''}
    ${homeSection('today') ? personalToday() : ''}
    ${homeSection('upcoming') ? `<section class="section" data-management-banner="upcoming">
      <div class="section-head"><h2>${homeSectionTitle('upcoming','Upcoming Events')}</h2><div class="button-row"><button class="text-button" data-build153-manage-contacts>Saved contacts</button></div></div>
      ${renderUpcomingGrouped(dashboard)}
    </section>` : ''}
  </section>`;
}

function sectionEventDate(event) {
  const day = event.start_at.slice(0, 10);
  if (event.all_day) return `${prettyDate(day, { weekday: 'short', day: 'numeric', month: 'short' })} · all day`;
  return `${prettyDate(day, { weekday: 'short', day: 'numeric', month: 'short' })} · ${event.start_at.slice(11,16)}–${event.end_at.slice(11,16)}`;
}
function eventSectionColour(event) {
  if (typeof safeColour !== 'function') return event.section_colour || event.location_colour || '#365CE6';
  const fromSection = event.section_id && (state.boot?.sections || []).find(section => Number(section.id) === Number(event.section_id))?.colour;
  return safeColour(event.section_colour || fromSection || event.colour);
}
function renderEventRow(event, {
  day = null,
  showDate = true,
  condensed = false,
  showLocation = true,
  index = 0,
} = {}) {
  const colour = eventSectionColour(event);
  const editable = event.origin !== 'Calendar' && event.section_id && event.id && !event.all_day;
  const attrs = editable
      ? ` data-week-action="event-edit" data-section-id="${event.section_id}" data-event-id="${event.id}" tabindex="0" role="button"`
      : eventViewAttributes(event);
  const travel = typeof eventTravelMarkup === 'function' ? eventTravelMarkup(event) : '';
  const contact = condensed ? '' : (window.ALIGN152?.eventContactMarkup(event.notes) || '');
  let timeLabel;
  if (event.all_day) timeLabel = 'All day';
  else if (day && event.start_at.slice(0, 10) < day) timeLabel = 'Continues';
  else if (showDate) timeLabel = escapeHtml(sectionEventDate(event).split(' · ')[0]);
  else timeLabel = escapeHtml(event.start_at.slice(11, 16));
  const until = !event.all_day && day && event.end_at.slice(0, 10) > day
    ? `${prettyDate(event.end_at.slice(0, 10))} ${event.end_at.slice(11, 16)}`
    : (event.end_at || '').slice(11, 16);
  const detailTime = !event.all_day
    ? (showDate ? ' · ' + escapeHtml(sectionEventDate(event).split(' · ').slice(1).join(' · ')) : (until ? ' · until ' + escapeHtml(until) : ''))
    : '';
  const areaOnly = eventChoice('title_format', 'location_area') === 'area';
  const shownTitle = event.title;
  const badgeName = event.category_name || event.calendar_name || '';
  const badgeColour = event.section_colour || colour;
  const badge = badgeName && typeof typeBadge === 'function' ? typeBadge(badgeName, badgeColour) : '';
  const meta = condensed
    ? badge
    : `${badge}<small>${showLocation && event.location ? appleDestinationLink(event.location) : ''}${detailTime}</small>`;
  const classes = [
    'card', 'week-event-row', 'upcoming-event', 'is-clickable',
    condensed ? 'event-condensed' : (index === 0 ? 'event-featured' : 'event-compact'),
  ].filter(Boolean).join(' ');
  return `<article class="${classes}" style="--section-colour:${escapeHtml(colour)}"${attrs}><div class="week-event-time">${timeLabel}</div><div><strong>${escapeHtml(shownTitle)}</strong>${meta}${contact}${travel}${!condensed && editable ? `<button type="button" class="small-button event-travel-button" data-week-action="event-travel" data-section-id="${event.section_id}" data-event-id="${event.id}">Add travel info</button>` : ''}</div></article>`;
}
function renderUpcomingEvent(event, index = 0, options = {}) {
  return renderEventRow(event, { index, ...options });
}
function eventLocationKey(event) {
  if (event.location_id) return `id:${event.location_id}`;
  if (event.location_name) return `name:${String(event.location_name).trim().toLowerCase()}`;
  if (event.kind === 'Work' || event.origin === 'Work') {
    const place = String(event.title || '').split(' · ')[0].trim().toLowerCase();
    if (place) return `name:${place}`;
  }
  const place = String(event.location || '').trim().toLowerCase();
  return place ? `name:${place}` : '';
}
function eventPlaceName(event) {
  return event.location_name || String(event.title || '').split(' · ')[0] || event.location || 'Event';
}
function renderGroupedEventRows(events, options = {}) {
  if (eventChoice('location_banner', 'on') === 'off') {
    return events.map((event, index) => renderUpcomingEvent(event, index, options)).join('');
  }
  const groups = [];
  for (const event of events) {
    const key = eventLocationKey(event);
    const last = groups[groups.length - 1];
    if (last && key && last.key === key) last.events.push(event);
    else groups.push({ key, events: [event] });
  }
  return groups.map(group => {
    const rows = group.events.map((event, index) => renderUpcomingEvent(event, index, options)).join('');
    if (group.events.length < 2) return rows;
    const first = group.events[0];
    const last = group.events[group.events.length - 1];
    const start = (first.start_at || '').slice(11, 16);
    const end = (last.end_at || '').slice(11, 16);
    const areas = [...new Set(group.events.map(event => event.category_name).filter(Boolean))];
    const place = eventPlaceName(first);
    const title = areas[0] || place;
    const badge = typeof typeBadge === 'function' ? typeBadge(place, eventSectionColour(first)) : escapeHtml(place);
    return `<section class="location-banner" style="--section-colour:${escapeHtml(eventSectionColour(first))}"><div class="location-banner-head"><div class="week-event-time">${escapeHtml(start)}–${escapeHtml(end)}</div><div><strong>${escapeHtml(title)}</strong>${badge}</div></div><div class="location-banner-items">${rows}</div></section>`;
  }).join('');
}
function renderUpcomingGrouped(dashboard) {
  const events = (dashboard.upcoming_events || []).filter(upcomingNow);
  const items = events.slice(0, 8);
  if (!items.length) {
    return '<div class="card empty">No upcoming events yet. Add your first one above.</div>';
  }
  const groupByDay = homeSectionContent('upcoming', 'group_by_day', true);
  if (!groupByDay) {
    return `<div class="upcoming-day-list"><div class="upcoming-day-items">${items.map((event, index) => renderUpcomingEvent(event, index, { showDate: true })).join('')}</div></div>`;
  }
  const groups = [];
  for (const event of items) {
    const last = groups[groups.length - 1];
    const day = event.start_at.slice(0, 10);
    if (!last || last.day !== day) groups.push({ day, events: [event] });
    else last.events.push(event);
  }
  return `<div class="upcoming-day-list">${groups.map(group => {
    return `<section class="upcoming-day"><h3 class="upcoming-day-heading">${escapeHtml(dayHeading(group.day))}</h3><div class="upcoming-day-items">${group.events.map((event, index) => renderUpcomingEvent(event, index, { showDate: false })).join('')}</div></section>`;
  }).join('')}</div>`;
}

function renderSection() {
  const section = state.sectionData;
  if (!section) return '<section class="page"><div class="card empty">Loading section…</div></section>';
  const now = new Date();
  const upcoming = section.events.filter(event => {
    const end = new Date(event.end_at);
    return Number.isFinite(end.getTime()) && end > now;
  });
  return `<section class="page">
    <div class="add-head section-detail-head" data-management-banner="section_detail" style="--section-colour:${escapeHtml(section.colour)}">
      <button class="text-button" data-action="section-home">‹ Sections</button>
      <p class="eyebrow">${escapeHtml(section.calendar_name ? `iCloud · ${section.calendar_name}` : 'Align section')}</p>
      <h1>${escapeHtml(section.icon)} ${escapeHtml(section.name)}</h1>
      <p class="subtle">${escapeHtml(section.description || 'Keep this part of your life together in one place.')}</p>
      <div class="button-row"><button class="primary-button" data-action="new-section-event">＋ Add event</button><button class="secondary-button" data-action="edit-section" data-id="${section.id}">Edit section</button></div>
    </div>
    <section class="section"><div class="section-head"><h2>Events</h2></div>
      <div class="master-list">${upcoming.map((event, index) => {
        const row = renderEventRow({
          ...event,
          section_id: section.id,
          section_colour: section.colour,
          category_name: section.name,
          origin: event.source_kind === 'icloud' ? 'Calendar' : 'Event',
          notes: event.notes || '',
        }, { showDate: true, index });
        const actions = event.source_kind === 'align'
          ? `<button class="small-button" data-action="edit-section-event" data-id="${event.id}">Edit</button>`
          : '';
        return actions ? row.replace('</article>', `${actions}</article>`) : row;
      }).join('') || '<div class="card empty">No upcoming events.</div>'}</div>
    </section>
  </section>`;
}

async function openSection(id) {
  state.sectionId = Number(id);
  state.sectionData = await api(`/api/sections/${state.sectionId}`);
  state.tab = 'section';
  render();
}

async function reloadSection() {
  if (!state.sectionId) return;
  state.sectionData = await api(`/api/sections/${state.sectionId}`);
  render();
}

function addressFields(target, name, value, label = 'Address') {
  return `<div class="field address-search"><label for="${target}-search">Find an address</label><div class="address-lookup-row"><input id="${target}-search" data-address-search="true" data-address-target="${target}" type="search" autocomplete="off" placeholder="Postcode, street or town" /><button class="secondary-button address-search-button" type="button" data-action="search-address" data-address-search-target="${target}-search">Search</button></div><div class="address-results" id="${target}-results" data-address-results="${target}"></div><small class="helper">Suggestions appear as you type. Tap one to fill the address, or keep typing it yourself below.</small></div><div class="field"><label for="${target}">${escapeHtml(label)}</label><textarea id="${target}" name="${name}" autocomplete="street-address" placeholder="Address">${escapeHtml(value)}</textarea></div>`;
}
function locationSearchField(value = '', name = 'location') {
  return `<div class="field address-search"><label for="event-location">Location</label><input id="event-location" name="${name}" maxlength="240" data-address-search="true" data-address-target="event-location" autocomplete="off" value="${escapeHtml(value || '')}" placeholder="Postcode, street or place" /><div class="address-results" id="event-location-results" data-address-results="event-location"></div><small class="helper">Suggestions appear as you type. Tap one to use it, or keep your own wording.</small><div class="event-location-link" data-event-location-link>${value ? appleDestinationLink(value) : ''}</div></div>`;
}

function renderOnboarding() {
  if (state.boot.builder) return builderStartup();
  const settings = state.boot.settings;
  const dataNote = state.boot.beta
    ? 'Your planner data belongs to this hosted account.'
    : 'This local app keeps its planner in the PC database. Admin backups are in PC Admin → Settings.';
  return `<section class="page onboarding"><div class="hero"><p class="eyebrow">First-time setup</p><h1>Let’s set up Align</h1><p class="subtle">Add your details once. You can change them later in Settings.</p><p class="subtle">${escapeHtml(dataNote)}</p></div>
    <form class="card settings-form" data-form="onboarding">
      <div><p class="eyebrow">About you</p><h2>Your details</h2></div>
      <div class="field"><label for="welcome-name">Name</label><input id="welcome-name" name="user_name" required autocomplete="name" value="${escapeHtml(settings.user_name)}" placeholder="Your name" /></div>
      ${addressFields('welcome-address', 'user_address', settings.user_address, 'Home address')}
      <p class="helper">You can set up Work as an optional database in Sections and edit it whenever you need.</p>
      <button class="primary-button">Continue to Align</button>
    </form>
  </section>`;
}

function renderLocalDataSettings() {
  if (state.boot.beta) return '';
  if (!isAdmin) {
    return `<section class="section"><div class="card settings-form"><h2>Local data &amp; backups</h2><p class="helper">This Align installation stores its planner data in a local SQLite database. Full database backups and restores are available only from the PC Admin page.</p></div></section>`;
  }
  return `<section class="section"><div class="card settings-form"><h2>Local data &amp; backups</h2><p class="helper">Download a private copy of this installation’s SQLite database; values stored in that database are included. Restore replaces the current database, so Align first saves an automatic pre-restore copy in the Master Backups folder. Disconnect iCloud before restoring. Separate key files and runtime files are not included or changed.</p><div class="button-row"><button type="button" class="secondary-button" data-action="download-local-backup">Download database backup</button></div><label class="field">Choose a backup to restore<input type="file" data-local-backup-file accept=".sqlite3,application/vnd.sqlite3"></label><p class="helper" role="status" aria-live="polite" data-local-backup-status></p></div></section>`;
}

function renderUserSettings() {
  const branches = [
    { branch_key: 'profile', title: 'Your details', description: 'Update your name and personal details.', icon: '○', branch_type: 'profile' },
    { branch_key: 'calendar', title: 'Calendar', description: 'Connect, import, or export your calendars.', icon: '▦', branch_type: 'calendar' },
  ];
  const permissions = state.boot.builder?.appearance_permissions || {};
  if (Object.values(permissions).some(Boolean)) {
    branches.push({
      branch_key: 'appearance', title: 'Personalise your app',
      description: 'Change the options made available for your account.',
      icon: '◐', branch_type: 'appearance'
    });
  }
  if (!branches.some(branch => branch.branch_key === state.settingsBranch)) state.settingsBranch = branches[0]?.branch_key || '';
  const selected = branches.find(branch => branch.branch_key === state.settingsBranch);
  return `<section class="page"><div class="add-head"><p class="eyebrow">Your planner</p><h1>Settings</h1><div class="button-row"><button data-nav="transport" class="secondary-button">Travel</button></div><p class="subtle">Your details, calendars and personal preferences.</p></div>
    <div class="settings-branch-list">${branches.map(branch => `<button class="card settings-branch ${branch.branch_key === state.settingsBranch ? 'selected' : ''}" data-action="settings-branch" data-branch="${escapeHtml(branch.branch_key)}"><span class="branch-icon">${escapeHtml(branch.icon)}</span><span><strong>${escapeHtml(branch.title)}</strong><small>${escapeHtml(branch.description)}</small></span><b>›</b></button>`).join('') || '<div class="card empty">No Settings branches are currently enabled.</div>'}</div>
    ${selected ? `<section class="section">${renderUserBranch(selected)}</section>` : ''}
    ${!isAdmin ? `<section class="section"><div class="card settings-form offline-tools-card"><div><p class="eyebrow">Offline support</p><h2>Offline diagnostics</h2></div><p class="helper">Check whether the app shell, phone database and saved planner responses are ready for use without the PC connection.</p><div class="button-row"><button type="button" class="secondary-button" data-action="offline-diagnostics">Open diagnostics</button><button type="button" class="primary-button" data-action="retry-offline-setup">Retry setup</button></div></div></section>` : ''}
    ${renderLocalDataSettings()}
    ${state.boot.beta ? `<section class="section"><div class="card settings-form"><p class="eyebrow">Account</p><h2>${escapeHtml(state.boot.beta.email)}</h2><p class="helper">Your planner and calendar data are stored in your own hosted account database. Database downloads and restores are disabled in hosted mode; this account’s data is not exposed to other persons.</p><div class="button-row"><button type="button" class="secondary-button" data-action="beta-feedback">Send feedback</button><button type="button" class="text-button" data-action="beta-logout">Sign out</button></div></div></section>` : ''}
  </section>`;
}

function renderUserBranch(branch) {
  if (branch.branch_type === 'profile' && state.boot.builder) return builderStartup(true);
  const settings = state.boot.settings;
  if (branch.branch_type === 'appearance') return renderPersonalAppearance();
  if (branch.branch_type === 'colours') return renderUserColours();
  if (branch.branch_type === 'work') return '<section class="card settings-form"><h2>Work</h2><p class="helper">Work is managed through the optional database in Sections.</p><button class="primary-button" data-nav="sections">Open Sections</button></section>';
  if (branch.branch_type === 'profile') return `<div class="section-head"><h2>${escapeHtml(branch.title)}</h2></div><form class="card settings-form" data-form="user-settings"><p class="helper">${escapeHtml(branch.description)}</p><div class="field"><label>Your name</label><input name="user_name" required value="${escapeHtml(settings.user_name)}" /></div>${addressFields('profile-address', 'user_address', settings.user_address)}<button class="primary-button">Save details</button></form>`;
  if (branch.branch_type === 'alerts') return renderAlertSettings();
  if (branch.branch_type === 'calendar') return renderCalendarSettings();
  if (branch.branch_type === 'locations') return '<section class="card settings-form"><h2>Work locations</h2><p class="helper">Work locations and areas are now fields in your optional Work database.</p><button class="primary-button" data-nav="sections">Open Sections</button></section>';
  return `<div class="section-head"><h2>${escapeHtml(branch.title)}</h2></div><article class="card info-card"><p class="helper">${escapeHtml(branch.description)}</p><p>${escapeHtml(branch.content || 'Your administrator has not added any information to this section yet.').replace(/\n/g, '<br>')}</p></article>`;
}

function renderPersonalAppearance() {
  const permissions = state.boot.builder?.appearance_permissions || {};
  const current = state.boot.builder?.appearance || {};
  const saved = state.boot.builder?.personal_appearance || {};
  const colorFields = (category, labels, values, prefix) => Object.entries(labels).map(([key, label]) =>
    `<label class="field"><span>${escapeHtml(label)}</span><input type="color" name="${prefix}_${key}" value="${escapeHtml(saved[category]?.[key] || values?.[key] || '#365ce6')}"></label>`
  ).join('');
  return `<section class="card settings-form"><h2>Personalise your app</h2><p class="helper">These choices apply only to your account.</p><form class="settings-form" data-form="user-appearance">
    ${permissions.colors ? `<fieldset><legend>App colours</legend>${colorFields('colors',{accent:'Accent',canvas:'Background',surface:'Cards',text:'Text'},current.colors,'color')}</fieldset>` : ''}
    ${permissions.banners ? `<fieldset><legend>Section banners</legend>${colorFields('banners',{today:'Today',upcoming:'Upcoming',annual_leave:'Annual leave',section_detail:'Personal sections'},current.banners,'banner')}</fieldset>` : ''}
    ${permissions.events ? `<fieldset><legend>Planner events</legend>${colorFields('events',{accent:'Event accent'},current.events,'event')}<label class="field">Event design<select name="events_style">${[['standard','Standard cards'],['compact','Compact'],['tinted','Tinted']].map(([key,label])=>`<option value="${key}" ${(saved.events?.style||current.events?.style)===key?'selected':''}>${label}</option>`).join('')}</select></label><label class="field">Spacing<select name="events_density">${[['comfortable','Comfortable'],['compact','Compact']].map(([key,label])=>`<option value="${key}" ${(saved.events?.density||current.events?.density)===key?'selected':''}>${label}</option>`).join('')}</select></label></fieldset>` : ''}
    ${permissions.calendar ? `<fieldset><legend>Calendar</legend>${colorFields('calendar',{month_cell:'Month day cells',month_weekend:'Month weekends',month_date_band:'Month date band',today_cell:'Today highlight',list_day:'List day cards',list_day_header:'List day headers'},current.calendar,'cal')}<label class="field">Week headings<select name="cal_week_headings">${[['show','Show'],['hide','Hide']].map(([key,label])=>`<option value="${key}" ${(saved.calendar?.week_headings||current.calendar?.week_headings)===key?'selected':''}>${label}</option>`).join('')}</select></label></fieldset>` : ''}
    ${permissions.type ? `<fieldset><legend>Text & shape</legend><label class="field">Text size<select name="type_scale">${[['default','Default'],['large','Larger']].map(([key,label])=>`<option value="${key}" ${(saved.type?.scale||current.type?.scale)===key?'selected':''}>${label}</option>`).join('')}</select></label><label class="field">Theme<select name="type_theme">${[['light','Light'],['dark','Dark'],['auto','Match my phone']].map(([key,label])=>`<option value="${key}" ${(saved.type?.theme||current.type?.theme)===key?'selected':''}>${label}</option>`).join('')}</select></label><label class="field">Font<select name="type_font">${[['system','Standard'],['serif','Serif'],['rounded','Rounded'],['mono','Monospace']].map(([key,label])=>`<option value="${key}" ${(saved.type?.font||current.type?.font)===key?'selected':''}>${label}</option>`).join('')}</select></label><label class="field">Headings<select name="type_heading">${[['bold','Bold'],['normal','Regular']].map(([key,label])=>`<option value="${key}" ${(saved.type?.heading||current.type?.heading)===key?'selected':''}>${label}</option>`).join('')}</select></label><label class="field">Corners<select name="type_corners">${[['soft','Soft'],['square','Square']].map(([key,label])=>`<option value="${key}" ${(saved.type?.corners||current.type?.corners)===key?'selected':''}>${label}</option>`).join('')}</select></label></fieldset>` : ''}
    <div class="button-row"><button class="primary-button">Save my appearance</button><button type="button" class="secondary-button" data-action="reset-user-appearance">Restore Align defaults</button></div><p class="helper" role="status" data-appearance-status></p>
  </form></section>`;
}

function renderAlertSettings() {
  return `<div class="section-head"><h2>Notifications</h2></div>
    <form class="card settings-form" data-form="user-settings"><div class="switch-row"><label for="user-notifications">Enable Align notifications</label><input class="switch" id="user-notifications" name="notifications" type="checkbox" ${state.boot.settings.notifications ? 'checked' : ''}/></div><p class="helper">This preference controls Align notifications for your account. Reminder times for events in an iCloud calendar are managed by that calendar.</p><div class="button-row"><button type="button" class="secondary-button" data-action="enable-browser-notifications">Enable notifications on this device</button><button class="primary-button">Save notification preference</button></div></form>`;
}

function renderCalendarSettings() {
  const feed = new URL(state.boot.calendar.feed_path, window.location.origin).href;
  const webcal = feed.replace(/^https?:/, 'webcal:');
  const localOnly = ['localhost', '127.0.0.1'].includes(window.location.hostname);
  return `${renderICloud()}<div class="section-head"><h2>Connect your calendar</h2></div><div class="card settings-form">
    <h3>Subscribe to Align</h3><p class="helper">Events added, changed or removed in Align are reflected when your calendar refreshes this subscription. Make changes in Align; this connection sends updates one way to Calendar.</p>
    <a class="primary-button calendar-link" href="${escapeHtml(webcal)}">Subscribe on iPhone</a>
    <div class="field"><label for="calendar-feed-url">Calendar subscription address</label><input id="calendar-feed-url" readonly value="${escapeHtml(feed)}"/><button type="button" class="secondary-button" data-action="copy-calendar-link">Copy subscription address</button></div>
    ${localOnly ? '<p class="apply-note">On your iPhone, open Align using the PC’s Wi-Fi address first. A 127.0.0.1 address points to the device viewing this page.</p>' : ''}
    <p class="helper">In iPhone Calendar: Calendars → Add Calendar → Add Subscription Calendar, then paste this address. Calendar controls refresh timing, so changes may take time to appear.</p>
    <p class="helper">${window.location.hostname === 'beta.getalign.co.uk' ? 'This hosted subscription works while your PC is off. Your calendar needs internet access to refresh it.' : 'For a local installation, keep the PC running and reachable on the same Wi-Fi. Updates away from home require a reachable HTTPS host.'}</p>
    <h3>Add a calendar file</h3><a class="secondary-button calendar-link" href="/api/calendars/align.ics" download="align-calendar.ics">Add ICS to Calendar</a><p class="helper">This file is a one-time copy. Use the subscription above for ongoing updates.</p>
    <form class="form-grid" data-form="calendar-import"><h3>Import a calendar into Align</h3><div class="field"><label>Calendar name</label><input name="name" placeholder="e.g. Personal calendar"/></div><div class="field"><label>Calendar file (.ics)</label><input name="ics_file" required type="file" accept=".ics,text/calendar"/></div><button class="secondary-button">Import and check for clashes</button><p class="helper">Imports are snapshots. Re-export your other calendar when you need fresh clash information.</p></form>
    </div><section class="section"><div class="section-head"><h2>Imported calendars</h2></div><div class="master-list">${state.boot.calendar.sources.map(source => `<article class="card master-item"><span class="branch-icon">▦</span><div class="item-content"><h3>${escapeHtml(source.name)}</h3><p>${source.event_count} imported events</p></div><button class="small-button" data-action="remove-calendar" data-id="${source.id}">Remove</button></article>`).join('') || '<div class="card empty">No calendars imported yet.</div>'}</div></section>`;
}

function alertRuleModal(id = null) {
  const rule = id ? state.boot.calendar.alert_rules.find(item => item.id === id) : { title: 'Time to Leave', minutes_before: 60, active: true };
  if (!rule) return;
  modal(id ? 'Edit alert' : 'Add alert', `<form class="form-grid" data-form="alert-rule" data-id="${id || ''}"><div class="field"><label for="alert-title">Alert name</label><input id="alert-title" name="title" required maxlength="80" value="${escapeHtml(rule.title)}"/></div><div class="field"><label for="alert-minutes">Remind me</label><select id="alert-minutes" name="minutes_before" required>${alertOffsetOptions(rule.minutes_before)}</select><small class="helper">Choose minutes, hours, days or a week before the event starts. 0 is not offered here — use a short offset for near-start alerts.</small></div><label class="switch-row"><span>Enable this alert</span><input class="switch" name="active" type="checkbox" ${rule.active ? 'checked' : ''}/></label><div class="modal-actions">${id ? `<button type="button" class="danger-button" data-action="delete-alert-rule" data-id="${id}">Delete</button>` : ''}<button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-button">Save alert</button></div></form>`);
}


function templateDays(template) {
  if (Array.isArray(template.applicable_days)) return template.applicable_days;
  try { return JSON.parse(template.applicable_days || '[]'); } catch (_) { return WEEK_DAYS; }
}
function templateAppliesOn(template, workDate) {
  const days = templateDays(template);
  return !days.length || days.includes(weekdayName(workDate));
}
function subShiftName(template) { return template?.sub_shift_type || template?.label || ''; }
function shiftPeriod(template) { return setupPeriod(template.start_time); }
function areaHasBothPeriods(template) {
  return new Set(state.boot.master.templates.filter(t => t.active && t.location_id === template.location_id && t.shift_type_id === template.shift_type_id).map(shiftPeriod)).size > 1;
}
function areaLabel(template) { return `${template.shift_type_name}${areaHasBothPeriods(template) ? ` (${shiftPeriod(template)})` : ''}`; }
function savedTimeLabel(template) { return `${template.start_time} + ${hours(timeHours(template.start_time, template.end_time))} → ${template.end_time}${template.break_minutes ? ` · ${template.break_minutes}m break` : ''}`; }
function templateSummary(template, includeTimes = true) {
  if (!template) return 'Shift';
  return `${template.location_name} · ${areaLabel(template)}${includeTimes ? ` · ${savedTimeLabel(template)}` : ''}`;
}
function draftFor(template, workDate) { return { work_date: workDate, template_id: template.id, start_time: template.start_time, end_time: template.end_time, break_minutes: template.break_minutes, notes: '' }; }
function assignedShifts() { return Object.values(state.add.assignments).flat(); }
function availableDraftTemplates(workDate, index = null) {
  const siblings = [...Object.entries(state.add.assignments).flatMap(([day, shifts]) => shifts.filter((_, i) => day !== workDate || i !== index)), ...(state.add.context?.busy_shifts || [])];
  if (state.add.context?.annual_leave.some(l => l.leave_date === workDate)) return [];
  return state.boot.master.templates
    // Add shifts is an explicit manual booking flow: a saved shift pattern
    // may be placed on any chosen date. Its configured weekdays remain useful
    // for recurring/setup views, but must not block one-off bookings.
    .filter(template => template.active)
    .filter(template => !siblings.some(draft => (draft.work_date === workDate && shiftPeriod(template) === shiftPeriod(draft)) || datedOverlap(draftFor(template, workDate), draft)))
    .filter(template => !(state.add.context?.imported_events || []).some(event => overlapsImported(draftFor(template, workDate), event)))
    .filter(template => !(state.add.context?.events || []).some(event => overlapsImported(draftFor(template, workDate), event)));
}

function renderLeaveCard(leave) { return `<article class="card leave-card"><div class="leave-icon">☼</div><div style="flex:1"><h3>${escapeHtml(prettyDate(leave.leave_date, { weekday: 'long', day: 'numeric', month: 'long' }))}</h3><p>${escapeHtml(leave.notes || 'Annual leave')}</p></div><button class="small-button" data-action="delete-leave" data-leave="${leave.id}">Remove</button></article>`; }
function groupLeaveRanges(days) {
  const groups = [];
  for (const leave of [...(days || [])].sort((a, b) => String(a.leave_date).localeCompare(String(b.leave_date)))) {
    const last = groups[groups.length - 1];
    const previous = last && last[last.length - 1];
    const sameNote = previous && (previous.notes || 'Annual leave') === (leave.notes || 'Annual leave');
    const nextDay = previous && (fromIso(leave.leave_date) - fromIso(previous.leave_date) === 86400000);
    if (sameNote && nextDay) last.push(leave);
    else groups.push([leave]);
  }
  return groups;
}
function leaveRangeLabel(group) {
  const format = date => fromIso(date).toLocaleDateString('en-GB');
  return group.length === 1 ? format(group[0].leave_date) : `${format(group[0].leave_date)}–${format(group[group.length - 1].leave_date)}`;
}
function renderLeaveRange(group) {
  return `<article class="card leave-card"><div class="leave-icon">☼</div><div style="flex:1"><h3>${escapeHtml(leaveRangeLabel(group))}</h3><p>${escapeHtml(group[0].notes || 'Annual leave')}</p></div><button class="small-button" data-action="delete-leave" data-leave="${group.map(leave => leave.id).join(',')}">Remove</button></article>`;
}

function renderMasterPanel() {
  if (state.masterTab === 'icloud') return renderICloud();
  const { settings, master } = state.boot;
  if (state.masterTab === 'setup') return `<section class="card settings-form"><h2>Work Settings</h2><p>View the same category lists as the user. Choose Add or Edit when required. Advanced controls remain in the other tabs.</p><button class="primary-button" data-action="work-setup">View Work Settings</button></section>`;
  if (state.masterTab === 'settings') return `<form class="card settings-form" data-form="settings"><div class="field"><label for="setting-name">Your display name</label><input id="setting-name" name="user_name" value="${escapeHtml(settings.user_name)}" placeholder="Your schedule" /></div><div class="field"><label for="setting-address">Home address</label><input id="setting-address" name="user_address" value="${escapeHtml(settings.user_address)}" placeholder="Optional" /></div><div class="field"><label for="rate-pay">Rate of pay (£)</label><input id="rate-pay" name="rate_of_pay" min="0" step="0.01" type="number" value="${settings.rate_of_pay}" /></div><div class="switch-row"><label for="notifications">Shift notifications</label><input class="switch" id="notifications" name="notifications" type="checkbox" ${settings.notifications ? 'checked' : ''} /></div><button class="primary-button">Save settings</button></form>`;
  if (state.masterTab === 'parent') return `<div class="master-list"><div class="master-banner" style="margin:0">This is the default menu tree. Create folders/submenus, move items between parents, change order, icons and colours. New testers inherit this structure; existing testers keep their personal sections.</div>${master.parents.map(branch => `<article class="card master-item ${branch.active ? '' : 'inactive'}"><span class="branch-icon">${escapeHtml(branch.icon)}</span><div class="item-content"><h3>${escapeHtml(branch.title)}</h3><p>${escapeHtml(branch.parent_title ? branch.parent_title + ' › ' : '')}${escapeHtml(branch.destination)} · order ${branch.sort_order}${branch.locked ? ' · locked' : ''}${branch.optional ? ' · optional' : ''}${branch.active ? '' : ' · hidden'}</p></div><button class="small-button" data-action="edit-parent-branch" data-id="${branch.id}">Edit</button></article>`).join('')}<button class="secondary-button" data-action="new-parent-branch">＋ Add Parent Menu branch</button></div>`;
  if (state.masterTab === 'locations') return `<div class="master-list">${master.locations.map(location => `<article class="card master-item ${location.active ? '' : 'inactive'}"><div class="item-content"><h3>${escapeHtml(location.name)}</h3><p>${escapeHtml(location.address || 'No address')} · ${escapeHtml(locationCategoryNames(location.id).join(', ') || 'No categories chosen')}</p></div><button class="small-button" data-action="edit-location" data-id="${location.id}">Edit</button></article>`).join('')}<button class="secondary-button" data-action="new-location">＋ Add location</button></div>`;
  if (state.masterTab === 'types') return `<div class="master-list">${master.shift_types.map(type => `<article class="card master-item ${type.active ? '' : 'inactive'}"><span class="colour-dot" style="position:static;background:${escapeHtml(type.colour)};width:13px;height:13px;flex:0 0 13px"></span><div class="item-content"><h3>${escapeHtml(type.name)}</h3><p>${type.active ? 'Available to use' : 'Hidden from new shifts'}</p></div><button class="small-button" data-action="edit-type" data-id="${type.id}">Edit</button></article>`).join('')}<button class="secondary-button" data-action="new-type">＋ Add shift type</button></div>`;
  if (state.masterTab === 'menus') return `<div class="master-list"><div class="master-banner" style="margin:0">These options make up the User app’s Settings menu. Standard branch types reveal the matching editable form; “Information” adds a custom read-only menu option.</div>${master.branches.map(branch => `<article class="card master-item ${branch.active ? '' : 'inactive'}"><span class="branch-icon">${escapeHtml(branch.icon)}</span><div class="item-content"><h3>${escapeHtml(branch.title)}</h3><p>${escapeHtml(branch.branch_type)} · order ${branch.sort_order}${branch.active ? '' : ' · hidden from users'}</p></div><button class="small-button" data-action="edit-menu-branch" data-id="${branch.id}">Edit</button></article>`).join('')}<button class="secondary-button" data-action="new-menu-branch">＋ Add menu branch</button></div>`;
  return `<div class="master-list">${master.templates.map(template => `<article class="card master-item ${template.active ? '' : 'inactive'}"><span class="colour-dot" style="position:static;background:${escapeHtml(template.colour)};width:13px;height:13px;flex:0 0 13px"></span><div class="item-content"><h3>${escapeHtml(template.location_name)} · ${escapeHtml(template.shift_type_name)} · ${escapeHtml(subShiftName(template))}</h3><p>${escapeHtml(template.start_time)}–${escapeHtml(template.end_time)} · ${escapeHtml(templateDays(template).join(', '))}${template.break_minutes ? ` · ${template.break_minutes}m break` : ''}</p></div><button class="small-button" data-action="edit-template" data-id="${template.id}">Edit</button></article>`).join('')}<button class="secondary-button" data-action="new-template">＋ Add shift pattern</button></div>`;
}

function timeHours(start, end) {
  const [sh, sm] = start.split(':').map(Number); const [eh, em] = end.split(':').map(Number);
  let total = eh * 60 + em - sh * 60 - sm; if (total <= 0) total += 1440; return total / 60;
}

function optionList(items, selectedId, label) { return items.map(item => `<option value="${item.id}" ${item.id === selectedId ? 'selected' : ''}>${escapeHtml(label(item))}</option>`).join(''); }
let modalReturnFocus = null;
function modal(title, content) {
  if (!modalRoot.firstElementChild) modalReturnFocus = document.activeElement;
  modalRoot.innerHTML = `<div class="modal-backdrop" data-action="close-modal"><section class="modal" role="dialog" aria-modal="true" tabindex="-1" aria-label="${escapeHtml(title)}"><div class="modal-head"><h2>${escapeHtml(title)}</h2><button class="close" data-action="close-modal" aria-label="Close">×</button></div>${content}</section></div>`;
  document.querySelector('.app-shell').inert = true;
  (modalRoot.querySelector('input:not([type=hidden]), select, textarea, button') || modalRoot.querySelector('[role=dialog]')).focus();
}
function closeModal() {
  modalRoot.innerHTML = '';
  document.querySelector('.app-shell').inert = false;
  if (modalReturnFocus?.isConnected) modalReturnFocus.focus();
  else app.focus();
  modalReturnFocus = null;
}
document.addEventListener('keydown', event => {
  const dialog = modalRoot.querySelector('[role=dialog]');
  if (!dialog) return;
  if (event.key === 'Escape') { event.preventDefault(); closeModal(); }
  if (event.key !== 'Tab') return;
  const items = [...dialog.querySelectorAll('button, a[href], input, select, textarea, [tabindex]')].filter(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length);
  const first = items[0], last = items[items.length - 1];
  if (!first) { event.preventDefault(); dialog.focus(); }
  else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});



function sectionModal(id = null) {
  const item = id ? state.boot.sections.find(section => section.id === id) : { name:'',description:'',icon:'•',colour:'#365CE6',calendar_id:'',import_enabled:1,export_enabled:1,sort_order:100,parent_branch_id:null };
  if (!item) return;
  const calendars = state.boot.icloud_public?.calendars || [];
  const folders = (state.boot.master.parents || []).filter(branch => branch.active && branch.destination === 'submenu');
  modal(id ? 'Edit section' : 'Add section', `<form class="form-grid" data-form="organiser-section" data-id="${id || ''}">
    <div class="form-grid two"><div class="field"><label>Section name</label><input name="name" required value="${escapeHtml(item.name)}" placeholder="e.g. Appointments" /></div><div class="field"><label>Icon</label><input name="icon" maxlength="4" value="${escapeHtml(item.icon || '•')}" /></div></div>
    <div class="field"><label>Description</label><input name="description" value="${escapeHtml(item.description || '')}" placeholder="What belongs here?" /></div>
    <div class="form-grid two"><div class="field"><label>Colour</label><input name="colour" type="color" value="${escapeHtml(item.colour || '#365CE6')}" /></div><div class="field"><label>Menu order</label><input name="sort_order" type="number" step="10" value="${item.sort_order || 100}" /></div></div>
    <div class="field"><label>Menu location</label><select name="parent_branch_id"><option value="">Home</option>${folders.map(f => `<option value="${f.id}" ${Number(item.parent_branch_id)===Number(f.id)?'selected':''}>Inside ${escapeHtml(f.title)}</option>`).join('')}</select><small class="helper">You can keep this on Home or place it inside a folder.</small></div>
    <div class="field"><label>iCloud calendar</label><select name="calendar_id"><option value="">No linked calendar</option>${calendars.map(c => `<option value="${c.id}" ${item.calendar_id===c.id?'selected':''}>${escapeHtml(c.name)}</option>`).join('')}</select><small class="helper">Connect your own iCloud account in Settings → Calendar before linking a section.</small><button type="button" class="small-button" data-personal="create-category-calendar">Create iCloud calendar for this category</button></div>
    <label class="switch-row"><span>Import iCloud events into this section</span><input class="switch" name="import_enabled" type="checkbox" ${item.import_enabled ? 'checked':''}/></label>
    <label class="switch-row"><span>Export Align events to this calendar</span><input class="switch" name="export_enabled" type="checkbox" ${item.export_enabled ? 'checked':''}/></label>
    <div class="modal-actions">${id ? `<button type="button" class="danger-button" data-action="delete-section" data-id="${id}">Delete</button>` : ''}<button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-button">Save section</button></div>
  </form>`);
}

function sectionEventModal(id = null) {
  const event = id ? state.sectionData?.events.find(item => item.source_kind === 'align' && item.id === id) : null;
  const calendars = state.boot?.icloud_event_calendars || [];
  const linked = state.boot?.sections.find(section => section.id === state.sectionId)?.calendar_id || '';
  const today = isoToday();
  const startAt = event?.start_at || `${today}T09:00`;
  const endAt = event?.end_at || `${today}T10:00`;
  modal(id ? 'Edit event' : `Add to ${state.sectionData?.name || 'section'}`, `<form class="form-grid" data-form="organiser-event" data-id="${id || ''}">
    <div class="field"><label>Which calendar would you like to add this to?</label><select name="calendar_id" ${calendars.length?'required':''}><option value="" ${!calendars.length?'selected':''}>${calendars.length?'Choose a calendar':'Align only · no iCloud calendar connected'}</option>${calendars.map(calendar => `<option value="${escapeHtml(calendar.id)}" ${calendar.id===linked?'selected':''}>${escapeHtml(calendar.name)}</option>`).join('')}${state.boot?.icloud_public?.connected?'<option value="__create__">＋ Create New Calendar</option>':''}</select><button type="button" class="small-button" data-personal="new-event-calendar" ${state.boot?.icloud_public?.connected?'':'disabled'}>＋ Create new calendar</button><small class="helper">Events saved to a calendar appear in its matching Section for quick access. Connect iCloud in Settings to add or select calendars.</small></div>
    <div class="field"><label>Event title</label><input name="title" required maxlength="160" value="${escapeHtml(event?.title || '')}" placeholder="e.g. Dentist" /></div>
    <div class="field"><label>Date</label><input name="date" type="date" required value="${escapeHtml(startAt.slice(0,10))}" /></div>
    <div class="form-grid two"><div class="field"><label>Start</label><input name="start_time" type="time" value="${escapeHtml(event?.all_day ? '09:00' : startAt.slice(11,16))}" /></div><div class="field"><label>End</label><input name="end_time" type="time" value="${escapeHtml(event?.all_day ? '10:00' : endAt.slice(11,16))}" /></div></div>
    <label class="switch-row"><span>All-day event</span><input class="switch" name="all_day" type="checkbox" ${event?.all_day ? 'checked' : ''}/></label>
    ${locationSearchField(event?.location || '')}
    ${travelNotesField(event?.notes || '')}${travelReminderFields(event?.notes)}<label class="setup-check"><input name="auto_travel" type="checkbox" checked>Automatically calculate and show travel times</label><p class="helper">On by default. Add a destination and start time; saving finds a journey from home and shows its walking and bus/train times on the event.</p>${travelCard(event?.notes || '')}<details><summary>Plan travel (optional)</summary>${eventTravelFields(event?.notes||'')}</details>
    <div class="modal-actions">${id ? `<button type="button" class="danger-button" data-action="delete-section-event" data-id="${id}">Delete</button>` : ''}<button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-button">Save event</button></div>
  </form>`);
  const journeyForm=modalRoot.querySelector('[data-form="organiser-event"]');
  journeyForm.querySelector('.modal-actions').insertAdjacentHTML('beforebegin',postTravelFields(event?.post_travel)+postTravelSummary(event||{}));
  if(event?.notes?.includes('[Align travel]'))journeyForm.journeySignature=journeyFormSignature(journeyForm);
}

function locationModal(id = null) {
  const item = id ? state.boot.master.locations.find(location => location.id === id) : { name: '', address: '', active: 1 };
  modal(id ? 'Edit location' : 'New location', `<form class="form-grid" data-form="location" data-id="${id || ''}"><div class="field"><label>Location name</label><input name="name" required value="${escapeHtml(item.name)}" placeholder="e.g. Main office" /></div>${addressFields('admin-location-address', 'address', item.address)}${locationColourField(item)}${locationCategoryPicker(id)}${id ? `<label class="switch-row"><span>Available for new shifts</span><input class="switch" name="active" type="checkbox" ${item.active ? 'checked' : ''}/></label>` : ''}<div class="modal-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-button">Save location</button></div></form>`);
}
function userLocationModal(id = null) {
  const item = id ? state.boot.master.locations.find(location => location.id === id) : { name: '', address: '' };
  modal(id ? 'Edit work location' : 'Add work location', `<form class="form-grid" data-form="user-location" data-id="${id || ''}"><p class="helper">Set the address, colour and categories. Use Work Settings to assign times and days.</p><div class="field"><label>Location name</label><input name="name" required value="${escapeHtml(item.name)}" placeholder="e.g. Main office" /></div>${addressFields('user-location-address', 'address', item.address)}${locationColourField(item)}${locationCategoryPicker(id)}<div class="modal-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-button">Save location</button></div></form>`);
}
function locationColourField(item) { return `<label class="field">Location colour<input name="colour" type="color" value="${escapeHtml(item.colour || '#365CE6')}"></label>`; }
function typeModal(id = null) {
  const item = id ? state.boot.master.shift_types.find(type => type.id === id) : { name: '', colour: '#3B82F6', active: 1 };
  modal(id ? 'Edit shift type' : 'New shift type', `<form class="form-grid" data-form="shift-type" data-id="${id || ''}"><div class="field"><label>Type name</label><input name="name" required value="${escapeHtml(item.name)}" placeholder="e.g. Clinic" /></div><div class="field"><label>Colour</label><input name="colour" type="color" value="${escapeHtml(item.colour)}" /></div>${id ? `<label class="switch-row"><span>Available for new shifts</span><input class="switch" name="active" type="checkbox" ${item.active ? 'checked' : ''}/></label>` : ''}<div class="modal-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-button">Save shift type</button></div></form>`);
}
function menuBranchModal(id = null) {
  const item = id ? state.boot.master.branches.find(branch => branch.id === id) : { title: '', description: '', icon: '○', branch_type: 'note', content: '', active: 1, sort_order: 100 };
  const types = [['profile', 'Your details'], ['work', 'Work Settings'], ['locations', 'Work locations'], ['colours', 'Colours'], ['alerts', 'Alerts'], ['calendar', 'Calendar'], ['note', 'Information only']];
  modal(id ? 'Edit menu branch' : 'Add menu branch', `<form class="form-grid" data-form="menu-branch" data-id="${id || ''}"><div class="form-grid two"><div class="field"><label>Menu label</label><input name="title" required value="${escapeHtml(item.title)}" placeholder="e.g. Helpful links" /></div><div class="field"><label>Icon</label><input name="icon" maxlength="4" value="${escapeHtml(item.icon)}" placeholder="○" /></div></div><div class="field"><label>Short description</label><input name="description" value="${escapeHtml(item.description)}" placeholder="Shown below the label" /></div><div class="form-grid two"><div class="field"><label>What this branch shows</label><select name="branch_type">${types.map(([key, label]) => `<option value="${key}" ${item.branch_type === key ? 'selected' : ''}>${label}</option>`).join('')}</select></div><div class="field"><label>Menu order</label><input name="sort_order" type="number" step="10" value="${item.sort_order}" /></div></div><div class="field"><label>Information text</label><textarea name="content" placeholder="Used by Information only branches; line breaks are kept.">${escapeHtml(item.content)}</textarea></div><label class="switch-row"><span>Show in User Settings</span><input class="switch" name="active" type="checkbox" ${item.active ? 'checked' : ''}/></label><div class="apply-note">Profile, Work, Locations and Notifications use the corresponding user-editable screen. Choose Information only to add a custom message or menu option.</div><div class="modal-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-button">Save menu branch</button></div></form>`);
}
function parentMenuBranchModal(id = null) {
  const item = id ? state.boot.master.parents.find(branch => branch.id === id) : { title:'',description:'',icon:'○',destination:'note',content:'',active:1,sort_order:100,parent_id:null,colour:'#365CE6',locked:0,optional:1 };
  const destinations=[['add','Add shifts'],['calendar','Schedule / Summary'],['settings','Settings'],['submenu','Submenu / folder'],['note','Information only']];
  const folders=(state.boot.master.parents || []).filter(branch => branch.destination === 'submenu' && branch.id !== id);
  modal(id ? 'Edit menu item' : 'Add menu item', `<form class="form-grid" data-form="parent-menu-branch" data-id="${id || ''}">
    <div class="form-grid two"><div class="field"><label>Menu label</label><input name="title" required value="${escapeHtml(item.title)}" /></div><div class="field"><label>Icon</label><input name="icon" maxlength="4" value="${escapeHtml(item.icon)}" /></div></div>
    <div class="field"><label>Short description</label><input name="description" value="${escapeHtml(item.description || '')}" /></div>
    <div class="form-grid two"><div class="field"><label>When selected</label><select name="destination">${destinations.map(([k,l])=>`<option value="${k}" ${item.destination===k?'selected':''}>${l}</option>`).join('')}</select></div><div class="field"><label>Colour</label><input name="colour" type="color" value="${escapeHtml(item.colour || '#365CE6')}" /></div></div>
    <div class="form-grid two"><div class="field"><label>Move inside</label><select name="parent_id"><option value="">Home / top level</option>${folders.map(f=>`<option value="${f.id}" ${Number(item.parent_id)===Number(f.id)?'selected':''}>${escapeHtml(f.title)}</option>`).join('')}</select></div><div class="field"><label>Order</label><input name="sort_order" type="number" step="10" value="${item.sort_order || 100}" /></div></div>
    <div class="field"><label>Information text</label><textarea name="content">${escapeHtml(item.content || '')}</textarea></div>
    <label class="switch-row"><span>Show in app</span><input class="switch" name="active" type="checkbox" ${item.active?'checked':''}/></label>
    <label class="switch-row"><span>Locked default</span><input class="switch" name="locked" type="checkbox" ${item.locked?'checked':''}/></label>
    <label class="switch-row"><span>Optional for testers</span><input class="switch" name="optional" type="checkbox" ${item.optional?'checked':''}/></label>
    <p class="helper">New testers inherit this structure. Existing testers keep their personal sections and colours when you later change the default tree.</p>
    <div class="modal-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-button">Save menu item</button></div></form>`);
}

function submenuModal(id) {
  const parent=state.boot.master.parents.find(branch=>branch.id===id); if(!parent) return;
  const branches=childParentBranches(id), sections=childSections(id);
  modal(parent.title, `<div class="quick-grid">${branches.map(branch=>`<button class="quick-action" data-action="parent-menu" data-id="${branch.id}" style="border-left:4px solid ${escapeHtml(branch.colour || '#365CE6')}"><b>${escapeHtml(branch.icon)}</b>${escapeHtml(branch.title)}<small>${escapeHtml(branch.description || '')}</small></button>`).join('')}${sections.map(section=>`<button class="quick-action organiser-section-tile" data-action="open-section" data-id="${section.id}" style="border-left:4px solid ${escapeHtml(section.colour)}"><b>${escapeHtml(section.icon)}</b>${escapeHtml(section.name)}<small>${escapeHtml(section.description || '')}</small></button>`).join('')}${!branches.length&&!sections.length?'<p class="helper">Nothing has been added here yet.</p>':''}</div><div class="modal-actions"><button class="primary-button" data-action="close-modal">Done</button></div>`);
}
function alignFeedbackModal(){ modal('Send feedback to Align', `<form class="form-grid" data-form="align-feedback"><div class="field"><label>Type</label><select name="type"><option value="problem">Problem</option><option value="idea">Idea</option><option value="general">General feedback</option></select></div><div class="field"><label>What would you like us to know?</label><textarea name="message" required maxlength="4000" rows="7"></textarea></div><p class="helper">Align build ${BUILD_VERSION} and the current screen can be included. Your planner/calendar content is not attached automatically.</p><div class="modal-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-button">Send feedback</button></div></form>`); }

function parentInfoModal(id) {
  const item = state.boot.master.parents.find(branch => branch.id === id);
  if (!item) return;
  modal(item.title, `<div class="info-card"><p class="helper">${escapeHtml(item.description)}</p><p>${escapeHtml(item.content || 'No information has been added to this menu branch yet.').replace(/\n/g, '<br>')}</p><div class="modal-actions"><button class="primary-button" data-action="close-modal">Done</button></div></div>`);
}
function locationCategoryIds(locationId) {
  return (state.boot.master.location_categories || {})[String(locationId)] || [];
}
function locationCategoryNames(locationId) {
  const ids = locationCategoryIds(locationId).map(Number);
  return state.boot.master.shift_types.filter(type => ids.includes(type.id)).map(type => type.name);
}
function locationCategoryPicker(locationId) {
  const selected = locationId ? locationCategoryIds(locationId).map(Number) : [];
  return `<div class="field"><label>Shift categories at this location</label><div class="category-picker">${state.boot.master.shift_types.filter(type => type.active).map(type => `<label class="category-option"><input name="shift_type_ids" type="checkbox" value="${type.id}" ${selected.includes(type.id) ? 'checked' : ''}/><span class="colour-dot" style="background:${escapeHtml(type.colour)}"></span><span>${escapeHtml(type.name)}</span></label>`).join('')}</div><small class="helper">Choose the categories used here. Admin then adds the saved AM/PM shift patterns and hours.</small></div>`;
}
function templateModal(id = null) {
  const item = id ? state.boot.master.templates.find(template => template.id === id) : { location_id: state.boot.master.locations[0]?.id, shift_type_id: state.boot.master.shift_types[0]?.id, sub_shift_type: '', applicable_days: [], start_time: '09:00', end_time: '17:00', break_minutes: 0, active: 1 };
  if (!item.location_id || !item.shift_type_id) { toast('Add a location and a shift type first.'); return; }
  const locations = optionList(state.boot.master.locations.filter(location => location.active), item.location_id, item => item.name);
  const types = optionList(state.boot.master.shift_types.filter(type => type.active), item.shift_type_id, item => item.name);
  const selectedDays = templateDays(item);
  const dayChoices = WEEK_DAYS.map(day => `<label class="weekday-option"><input name="applicable_days" type="checkbox" value="${day}" ${selectedDays.includes(day) ? 'checked' : ''}/><span>${day.slice(0, 3)}</span></label>`).join('');
  modal(id ? 'Edit shift pattern' : 'New shift pattern', `<form class="form-grid" data-form="template" data-id="${id || ''}"><p class="helper">Set the exact choices users see in this order: location, shift type, sub-shift, then times.</p><div class="field"><label>Where</label><select name="location_id">${locations}</select></div><div class="field"><label>Shift type</label><select name="shift_type_id">${types}</select></div><div class="field"><label>Sub-shift type</label><input name="sub_shift_type" required value="${escapeHtml(subShiftName(item))}" placeholder="e.g. AM or PM" /></div><div class="form-grid two"><div class="field"><label>Start time</label><input name="start_time" required type="time" value="${escapeHtml(item.start_time)}" /></div><div class="field"><label>End time</label><input name="end_time" required type="time" value="${escapeHtml(item.end_time)}" /></div></div><div class="field"><label>Days this pattern applies to</label><div class="weekday-picker">${dayChoices}</div></div><div class="field"><label>Unpaid break (minutes)</label><input name="break_minutes" min="0" type="number" value="${item.break_minutes}" /></div>${id ? `<label class="switch-row"><span>Available for new shifts</span><input class="switch" name="active" type="checkbox" ${item.active ? 'checked' : ''}/></label><div class="apply-note">Changing a pattern affects future selections only. You can separately apply its details to future scheduled shifts.</div>` : ''}<div class="modal-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-button">Save shift pattern</button></div></form>${id ? `<button class="text-button" style="margin-top:11px" data-action="apply-template" data-id="${id}">Apply this pattern to future scheduled shifts</button>` : ''}`);
}
function applyTemplateModal(id) { modal('Apply master template', `<form class="form-grid" data-form="apply-template" data-id="${id}"><p class="helper">This is deliberate: it updates the times, type and location on future shifts made from this template. Notes stay unchanged.</p><div class="field"><label>Update shifts on or after</label><input name="from_date" type="date" value="${isoToday()}" /></div><div class="modal-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-button">Apply to future shifts</button></div></form>`); }
function renderLeaveBalance(balance) {
  if (!balance?.allowance) return '';
  const over = balance.remaining < 0;
  return `<p class="helper">${balance.booked} days booked from ${escapeHtml(prettyDate(balance.year_start))} to ${escapeHtml(prettyDate(balance.year_end))}. ${over ? `${-balance.remaining} over the ${balance.allowance}-day allowance` : `${balance.remaining} of ${balance.allowance} days left`}.</p>`;
}
function coverFromNotes(notes = '') {
  const match = String(notes || '').match(/\[Align cover: (given|extra)(?:\s+([^\]]+))?\]/i);
  return {cover: match ? match[1].toLowerCase() : '', name: match ? (match[2] || '').trim() : ''};
}
function leaveModal() {
  const balance = state.boot.dashboard.leave_balance;
  const note = balance?.allowance ? renderLeaveBalance(balance) : '<p class="helper">Set a yearly leave allowance in Work Settings to see how many days are left.</p>';
  modal('Book annual leave', `<form class="form-grid" data-form="leave">${note}<div class="form-grid two"><div class="field"><label>From</label><input name="start_date" required type="date" min="${isoToday()}" value="${isoToday()}" /></div><div class="field"><label>To</label><input name="end_date" required type="date" min="${isoToday()}" value="${isoToday()}" /></div></div><div class="field"><label>Notes (optional)</label><textarea name="notes" placeholder="e.g. Holiday"></textarea></div><div class="modal-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button class="primary-button">Book leave</button></div></form>`);
}
function localShiftsOverlap(first, second) {
  const range = value => { const [startHour, startMinute] = value.start_time.split(':').map(Number); const [endHour, endMinute] = value.end_time.split(':').map(Number); const start = startHour * 60 + startMinute; let end = endHour * 60 + endMinute; if (end <= start) end += 1440; return [start, end]; };
  const [aStart, aEnd] = range(first); const [bStart, bEnd] = range(second); return aStart < bEnd && bStart < aEnd;
}

const addressSearchTimers = new WeakMap();
async function searchAddresses(input) {
  const target = input.dataset.addressTarget;
  const results = document.querySelector(`[data-address-results="${target}"]`);
  const query = input.value.trim();
  if (!results) return;
  if (query.length < 3) { results.innerHTML = ''; return; }
  results.innerHTML = '<p class="address-status">Finding UK addresses…</p>';
  try {
    const payload = await api(`/api/address-search?q=${encodeURIComponent(query)}`);
    if (input.value.trim() !== query) return;
    results.innerHTML = payload.results.length ? payload.results.map(result => `<button type="button" class="address-result" data-action="choose-address" data-address-target="${target}" data-address="${encodeURIComponent(result.label)}">${escapeHtml(result.label)}</button>`).join('') : '<p class="address-status">No matches. You can enter the address manually.</p>';
  } catch (error) {
    results.innerHTML = `<p class="address-status">${escapeHtml(error.message)}</p>`;
  }
}

document.addEventListener('click', async event => {
  if (event.target.closest('.compact-event-details')) return;
  if (event.target.closest('.apple-maps-link')) return;
  const element = event.target.closest('[data-action], [data-nav], [data-section-key]');
  if (!element) return;
  if (element.dataset.sectionKey) { await builderOpenLayout(element.dataset.sectionKey); return; }
  if (element.dataset.nav) { if (workSetup?.saving) return; if (workSetup?.editor && !window.confirm('Discard this unsaved Work Settings edit?')) return; workSetup = null; state.tab = element.dataset.nav; render(); return; }
  const action = element.dataset.action;
  if (action === 'prompt-install') { void promptAlignInstall(); return; }
  if (action === 'download-local-backup') {
    try {
      const response = await fetch('/api/local-backup', { headers: adminToken ? { 'X-Align-Admin': adminToken } : {} });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || 'The database backup could not be downloaded.');
      }
      const blob = await response.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || 'align-backup.sqlite3';
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
      toast('Local database backup downloaded. Keep the file private.');
    } catch (error) { toast(error.message); }
    return;
  }
  if (action === 'offline-diagnostics') { await showOfflineDiagnostics(); return; }
  if (action === 'enable-browser-notifications') { try { await enableBrowserNotifications(); } catch (error) { toast(error.message); } return; }
  if (action === 'retry-offline-setup') { closeModal(); await completeOfflineSetup({ showResult: true }); return; }
  if (action === 'beta-feedback') { alignFeedbackModal(); return; }
  if (action === 'beta-logout') { try { await rawApi('/api/beta/logout',{method:'POST',body:{}}); if(typeof AlignOffline!=='undefined' && AlignOffline.reset) await AlignOffline.reset(); if(navigator.serviceWorker?.controller) navigator.serviceWorker.controller.postMessage({type:'ALIGN_CLEAR_PRIVATE'}); } finally { location.href='/login'; } return; }
  if (action === 'new-section') { sectionModal(); return; }
  if (action === 'open-section') { try { await openSection(Number(element.dataset.id)); } catch (error) { toast(error.message); } return; }
  if (action === 'section-home') { state.tab = 'sections'; state.sectionData = null; state.sectionId = null; render(); return; }
  if (action === 'edit-section') { sectionModal(Number(element.dataset.id)); return; }
  if (action === 'new-section-event') { personalAvailability(state.sectionId); return; }
  if (action === 'edit-section-event') { sectionEventModal(Number(element.dataset.id)); return; }
  if (action === 'delete-section') {
    if (!window.confirm('Delete this section and its Align-created events? iCloud events themselves are left alone.')) return;
    try { await api(`/api/sections/${element.dataset.id}`, { method: 'DELETE' }); closeModal(); state.sectionData = null; state.sectionId = null; state.tab = 'sections'; await refresh(); toast('Section deleted.'); } catch (error) { toast(error.message); }
    return;
  }
  if (action === 'delete-section-event') {
    if (!window.confirm('Delete this event from Align and its linked iCloud calendar?')) return;
    try { await api(`/api/organiser-events/${element.dataset.id}`, { method: 'DELETE' }); closeModal(); await refresh(); await reloadSection(); toast('Event deleted.'); } catch (error) { toast(error.message); }
    return;
  }
  if (action === 'work-setup') { state.tab='sections'; render(); return; }
  if (action === 'reload-app') { window.location.reload(); return; }
  if (action === 'go-calendar-settings') { state.settingsBranch = 'calendar'; state.tab = 'settings'; render(); }
  if (action === 'new-alert-rule') alertRuleModal();
  if (action === 'edit-alert-rule') alertRuleModal(Number(element.dataset.id));
  if (action === 'delete-alert-rule') {
    if (!window.confirm('Remove this alert from upcoming events and the Align calendar?')) return;
    try { await api(`/api/alert-rules/${element.dataset.id}`, { method: 'DELETE' }); closeModal(); await refresh(); toast('Alert removed.'); } catch (error) { toast(error.message); }
  }
  if (action === 'copy-calendar-link') {
    const input = document.querySelector('#calendar-feed-url');
    try { await navigator.clipboard.writeText(input.value); toast('Subscription address copied.'); }
    catch (_) { input.focus(); input.select(); toast(document.execCommand('copy') ? 'Subscription address copied.' : 'Select and copy the subscription address above.'); }
  }

  if (action === 'go-master') { state.tab = 'master'; render(); }
  if (action === 'work-opt-in') {
    const work = state.sectionDefinitions.find(section => section.key === 'work');
    if (!work) { toast('Work setup is not available yet. The Work database will appear here when it is ready.'); return; }
    try {
      await api('/api/builder/records/work/enable', {method:'POST', body:{}});
      state.sectionDefinitions = (await api('/api/sections/definitions')).sections || [];
      await builderOpenLayout('work');
    } catch (error) { toast(error.message); }
    return;
  }
  if (action === 'go-settings') { state.tab = 'settings'; render(); }
  if (action === 'parent-menu') {
    const branch = state.boot.master.parents.find(item => item.id === Number(element.dataset.id));
    if (!branch) return;
    if (branch.destination === 'note') parentInfoModal(branch.id);
    else if (branch.destination === 'submenu') submenuModal(branch.id);
    else { state.tab = branch.destination; render(); }
  }
  if (action === 'close-modal') {
    if (element.classList.contains('modal-backdrop') && event.target !== element) return;
    closeModal();
  }
  if (action === 'choose-address') {
    const target = document.getElementById(element.dataset.addressTarget);
    if (target) {
      target.value = decodeURIComponent(element.dataset.address);
      target.dispatchEvent(new Event('input', {bubbles: true}));
      target.focus();
      const link = target.closest('.address-search')?.querySelector('[data-event-location-link]');
      if (link) link.innerHTML = target.value ? appleDestinationLink(target.value) : '';
    }
    const results = document.querySelector(`[data-address-results="${element.dataset.addressTarget}"]`);
    if (results) results.innerHTML = '';
  }
  if (action === 'search-address') {
    const input = document.getElementById(element.dataset.addressSearchTarget);
    if (input) searchAddresses(input);
  }
  if (action === 'master-tab') { state.masterTab = element.dataset.masterTab; render(); }
    if (action === 'settings-branch') { state.settingsBranch = element.dataset.branch; render(); }
  if (action === 'reset-user-appearance') {
    try {
      const result = await api('/api/user-appearance', { method: 'PUT', body: { reset: true } });
      state.boot.builder.appearance = result.appearance;
      state.boot.builder.personal_appearance = result.personal_appearance;
      render();
      toast('Align defaults restored.');
    } catch (error) { toast(error.message); }
    return;
  }
  if (action === 'new-location') locationModal();
  if (action === 'edit-location') locationModal(Number(element.dataset.id));
  if (action === 'new-user-location') userLocationModal();
  if (action === 'edit-user-location') userLocationModal(Number(element.dataset.id));
  if (action === 'new-menu-branch') menuBranchModal();
  if (action === 'edit-menu-branch') menuBranchModal(Number(element.dataset.id));
  if (action === 'new-parent-branch') parentMenuBranchModal();
  if (action === 'edit-parent-branch') parentMenuBranchModal(Number(element.dataset.id));
  if (action === 'new-type') typeModal();
  if (action === 'edit-type') typeModal(Number(element.dataset.id));
  if (action === 'new-template') templateModal();
  if (action === 'edit-template') templateModal(Number(element.dataset.id));

  if (action === 'delete-leave') {
    const ids = String(element.dataset.leave || '').split(',').filter(Boolean);
    if (!ids.length || !window.confirm(ids.length > 1 ? 'Remove this annual leave?' : 'Remove this annual leave day?')) return;
    try {
      for (const id of ids) await api(`/api/leave/${id}`, { method: 'DELETE' });
      await refresh(); toast('Annual leave removed.');
    } catch (error) { toast(error.message); }
  }
  if (action === 'remove-calendar') {
    if (!window.confirm('Remove this imported calendar and its clash checks?')) return;
    try { await api(`/api/calendars/${element.dataset.id}`, { method: 'DELETE' }); await refresh(); toast('Imported calendar removed.'); } catch (error) { toast(error.message); }
  }
});

document.addEventListener('change', async event => {
  const input = event.target.closest('[data-local-backup-file]');
  const file = input?.files?.[0];
  if (!input || !file) return;
  const status = document.querySelector('[data-local-backup-status]');
  if (file.size > 100 * 1024 * 1024) {
    if (status) status.textContent = 'Choose a backup smaller than 100 MB.';
    input.value = '';
    return;
  }
  if (!window.confirm('Restore this Align backup? It will replace all planner data in this local database. Align first saves an automatic pre-restore copy. Credentials and provider settings are separate and will not change.')) {
    input.value = '';
    return;
  }
  if (status) status.textContent = 'Checking and restoring the database…';
  input.disabled = true;
  try {
    const response = await fetch('/api/local-backup/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/vnd.sqlite3', ...(adminToken ? { 'X-Align-Admin': adminToken } : {}) },
      body: file,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || 'The backup could not be restored.');
    if (status) status.textContent = 'Restore complete. Reloading Align…';
    setTimeout(() => window.location.reload(), 500);
  } catch (error) {
    if (status) status.textContent = error.message;
  } finally {
    input.disabled = false;
    input.value = '';
  }
});

document.addEventListener('input', event => {
  const field = event.target.dataset.addField;
  if (field) state.add[field] = event.target.type === 'number' ? Number(event.target.value) : event.target.value;
  if (event.target.hasAttribute('data-address-search')) {
    window.clearTimeout(addressSearchTimers.get(event.target));
    addressSearchTimers.set(event.target, window.setTimeout(() => searchAddresses(event.target), 420));
  }
});

document.addEventListener('change', event => {
  const form = event.target.closest('form');
  if (!event.target.matches('[data-template-select]')) return;
  const template = state.boot.master.templates.find(item => item.id === Number(event.target.value));
  if (!template || !form) return;
  form.start_time.value = template.start_time;
  form.end_time.value = template.end_time;
  form.break_minutes.value = template.break_minutes;
});

document.addEventListener('keydown', event => {
  if (event.key === 'Enter' && event.target.hasAttribute('data-address-search')) {
    event.preventDefault();
    searchAddresses(event.target);
  }
});

document.addEventListener('input', event => {
  const field = event.target;
  if (!field?.matches?.('input, select, textarea')) return;
  field.removeAttribute('aria-invalid');
});

document.addEventListener('invalid', event => {
  const field = event.target;
  const form = field?.form;
  if (!form) return;
  const tracked = form.dataset.form || ['travel150', 'assets-upload150'].includes(form.id);
  if (!tracked) return;
  field.setAttribute('aria-invalid', 'true');
  showFormError(form, 'Check the highlighted fields and try again.');
}, true);

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!form.dataset.form) return;
  event.preventDefault();
  form.querySelector('[data-form-error]')?.remove();
  if (typeof form.checkValidity === 'function' && !form.checkValidity()) {
    form.querySelectorAll(':invalid').forEach(field => field.setAttribute('aria-invalid', 'true'));
    const invalid = form.querySelector(':invalid');
    invalid?.focus();
    showFormError(form, 'Check the highlighted fields and try again.');
    form.reportValidity();
    return;
  }
  const values = Object.fromEntries(new FormData(form));
  try {
    if (form.dataset.form === 'admin-login') {
      const result = await api('/api/admin/login', { method: 'POST', body: values });
      adminToken = result.token;
      sessionStorage.setItem('align-admin-token', adminToken);
      await refresh();
      toast('Admin access unlocked.');
      return;
    }
    if (form.dataset.form === 'organiser-section') {
      const id = form.dataset.id;
      values.import_enabled = form.import_enabled.checked;
      values.export_enabled = form.export_enabled.checked;
      values.sort_order = Number(values.sort_order || 100);
      values.parent_branch_id = values.parent_branch_id ? Number(values.parent_branch_id) : null;
      await api(id ? `/api/sections/${id}` : '/api/sections', { method: id ? 'PUT' : 'POST', body: values });
      closeModal(); await refresh();
      if (id) await openSection(Number(id));
      toast(id ? 'Section updated.' : 'Section added.');
      return;
    }
    if (form.dataset.form === 'organiser-event') {
      if (!state.sectionId) throw new Error('Open a section first.');
      const id = form.dataset.id;
      const allDay = form.all_day.checked;
      const body = { title: values.title, all_day: allDay, calendar_id: values.calendar_id, location: values.location || '', notes: travelReminderNotes(values.notes, allDay ? '' : values.travel_reminder) };
      body.show_post_travel=form.show_post_travel.checked;body.post_travel_mode=form.post_travel_mode.value;
      if (allDay) body.date = values.date;
      else { body.start_at = `${values.date}T${values.start_time}`; body.end_at = `${values.date}T${values.end_time}`; }
      let travelWarning = '';
      if (!allDay && form.auto_travel?.checked && body.location.trim() && (form.journeySignature !== journeyFormSignature(form) || !body.notes.includes('[Align travel]'))) {
        try {
          const prefs = personalPrefs();
          const journey = await api('/api/personal/journey', { method: 'POST', body: {
            destination: body.location,
            arrival: body.start_at,
            ...(values.journey_origin === 'phone' ? await phoneLocation() : {}),
            mode: values.journey_mode || prefs.default_travel || 'transit',
            departure_buffer: Number(values.departure_buffer ?? prefs.departure_buffer ?? 5),
            arrival_buffer: Number(values.arrival_buffer ?? prefs.arrival_buffer ?? 10)
          }});
          const plan = journey.journeys?.[0];
          if (!plan?.notes) throw new Error('No suitable journey was found.');
          if (plan?.notes) body.notes = `${body.notes.replace(/\n?\[Align travel steps\][\s\S]*?(?:\[\/Align travel steps\]|$)/ig, '').replace(/\n?\[Align travel\][\s\S]*?(?:\[\/Align travel\]|$)/ig, '').trim()}\n[Align travel]\n${plan.notes}\n[/Align travel]${plan.steps?.length ? `\n[Align travel steps]\n${JSON.stringify(plan.steps)}\n[/Align travel steps]` : ''}`.trim();
        } catch (error) {
          travelWarning = ` Event saved, but automatic travel details were unavailable: ${error.message}`;
        }
      }
      if (!id) {
        form.dataset.requestId ||= (crypto.randomUUID ? crypto.randomUUID() : `section-${Date.now()}-${Math.random().toString(16).slice(2)}`);
        body.request_id = form.dataset.requestId;
      }
      const result = await api(id ? `/api/organiser-events/${id}` : `/api/sections/${state.sectionId}/events`, { method: id ? 'PUT' : 'POST', body });
      if(!result.offline){try{const warning=await savePostTravel('event',id||result.id,form);if(warning)travelWarning+=' Post event travel: '+warning;}catch(error){travelWarning+=' Post event travel could not be saved: '+error.message;}}
      if (result.section_id) state.sectionId = Number(result.section_id);
      closeModal(); await refresh(); await reloadSection();       toast((id ? 'Event updated.' : (result.offline ? 'Saved offline. It will sync to iCloud when Align reconnects.' : 'Event added. iCloud sync will pick it up shortly.')) + travelWarning);
      return;
    }
    if (form.dataset.form === 'align-feedback') { await api('/api/beta/feedback',{method:'POST',body:{type:values.type,message:values.message,screen:state.tab}}); closeModal(); toast('Feedback sent to Align — thank you.'); return; }
    if (form.dataset.form === 'transport-plan') { throw new Error('Choose a saved shift or event and locations in the Travel screen before finding journeys.'); }
    if (form.dataset.form === 'alert-rule') {
      values.active = form.active.checked;
      values.minutes_before = Number(values.minutes_before);
      await api(form.dataset.id ? `/api/alert-rules/${form.dataset.id}` : '/api/alert-rules', { method: form.dataset.id ? 'PUT' : 'POST', body: values });
      closeModal(); await refresh(); toast('Alert saved for upcoming events.');
    }
    if (form.dataset.form === 'onboarding') { values.onboarding_completed = true; await api('/api/user-settings', { method: 'PUT', body: values }); await refresh(); }
      if (form.dataset.form === 'user-appearance') {
        const permissions = state.boot.builder?.appearance_permissions || {};
        const appearance = {};
        if (permissions.colors) appearance.colors = Object.fromEntries(['accent', 'canvas', 'surface', 'text'].map(key => [key, values[`color_${key}`]]));
        if (permissions.banners) appearance.banners = Object.fromEntries(['today', 'upcoming', 'annual_leave', 'section_detail'].map(key => [key, values[`banner_${key}`]]));
        if (permissions.events) appearance.events = {
          accent: values.event_accent, style: values.events_style, density: values.events_density
        };
        if (permissions.calendar) appearance.calendar = {...Object.fromEntries(['month_cell','month_weekend','month_date_band','today_cell','list_day','list_day_header'].map(key => [key, values[`cal_${key}`]])), week_headings: values.cal_week_headings};
        if (permissions.type) appearance.type = {scale: values.type_scale, corners: values.type_corners, font: values.type_font, theme: values.type_theme, heading: values.type_heading};
        const result = await api('/api/user-appearance', {method: 'PUT', body: {appearance}});
        state.boot.builder.appearance = result.appearance;
        state.boot.builder.personal_appearance = result.personal_appearance;
        render();
        toast('Your appearance preferences are saved to your account.');
        return;
      }
      if (form.dataset.form === 'user-settings') { if (form.notifications) values.notifications = form.notifications.checked; await api('/api/user-settings', { method: 'PUT', body: values }); await refresh(); toast('Settings saved.'); }
    if (form.dataset.form === 'settings') { values.notifications = form.notifications.checked; await api('/api/settings', { method: 'PUT', body: values }); await refresh(); toast('Master settings saved.'); }
    if (form.dataset.form === 'user-location') { const id = form.dataset.id; values.shift_type_ids = [...form.querySelectorAll('input[name="shift_type_ids"]:checked')].map(input => Number(input.value)); await api(id ? `/api/user-locations/${id}` : '/api/user-locations', { method: id ? 'PUT' : 'POST', body: values }); closeModal(); await refresh(); toast('Work location saved.'); }
    if (form.dataset.form === 'location') { const id = form.dataset.id; values.active = form.active ? form.active.checked : true; values.shift_type_ids = [...form.querySelectorAll('input[name="shift_type_ids"]:checked')].map(input => Number(input.value)); await api(id ? `/api/locations/${id}` : '/api/locations', { method: id ? 'PUT' : 'POST', body: values }); closeModal(); await refresh(); toast('Location saved.'); }
    if (form.dataset.form === 'menu-branch') { const id = form.dataset.id; values.active = form.active.checked; await api(id ? `/api/menu-branches/${id}` : '/api/menu-branches', { method: id ? 'PUT' : 'POST', body: values }); closeModal(); await refresh(); toast('User menu branch saved.'); }
    if (form.dataset.form === 'parent-menu-branch') { const id = form.dataset.id; values.active = form.active.checked; values.locked=form.locked.checked; values.optional=form.optional.checked; values.parent_id=values.parent_id ? Number(values.parent_id) : null; values.sort_order=Number(values.sort_order || 100); await api(id ? `/api/parent-menu-branches/${id}` : '/api/parent-menu-branches', { method: id ? 'PUT' : 'POST', body: values }); closeModal(); await refresh(); toast('Parent Menu branch saved.'); }
    if (form.dataset.form === 'calendar-import') { const file = form.ics_file.files[0]; if (!file) throw new Error('Choose an .ics calendar file first.'); const ics = await file.text(); await api('/api/calendars/import', { method: 'POST', body: { name: values.name || file.name.replace(/\.ics$/i, ''), ics } }); await refresh(); toast('Calendar imported. Events can now be checked against it.'); }
    if (form.dataset.form === 'shift-type') { const id = form.dataset.id; values.active = form.active ? form.active.checked : true; await api(id ? `/api/shift-types/${id}` : '/api/shift-types', { method: id ? 'PUT' : 'POST', body: values }); closeModal(); await refresh(); toast('Shift type saved.'); }
    if (form.dataset.form === 'template') { const id = form.dataset.id; values.active = form.active ? form.active.checked : true; values.applicable_days = [...form.querySelectorAll('input[name="applicable_days"]:checked')].map(input => input.value); if (!values.applicable_days.length) throw new Error('Choose at least one day for this shift pattern.'); await api(id ? `/api/templates/${id}` : '/api/templates', { method: id ? 'PUT' : 'POST', body: values }); closeModal(); await refresh(); toast('Shift pattern saved.'); }
    if (form.dataset.form === 'leave') {
      const booked = await api('/api/leave', { method: 'POST', body: values });
      closeModal(); await refresh();
      const balance = booked.leave_balance;
      toast(balance?.allowance ? (balance.remaining < 0 ? `Annual leave booked. That is ${-balance.remaining} day${balance.remaining === -1 ? '' : 's'} over the allowance.` : `Annual leave booked. ${balance.remaining} day${balance.remaining === 1 ? '' : 's'} left.`) : 'Annual leave booked.');
    }
  } catch (error) { showFormError(form, error.message); toast(error.message, 'error'); }
});

function renderAdminLogin(message = '') {
  app.innerHTML = `<section class="page"><div class="hero"><p class="eyebrow">PC workspace</p><h1>Admin access</h1><p class="subtle">Sign in to edit locations, shift templates, work settings and future scheduled shifts.</p></div><form class="card settings-form" data-form="admin-login"><div class="field"><label for="admin-password">Admin password</label><input id="admin-password" name="password" required type="password" autocomplete="current-password" autofocus /></div>${message ? `<p class="helper" style="color:#c6435b;margin:0">${escapeHtml(message)}</p>` : ''}<button class="primary-button">Open Master Edit</button><p class="helper" style="margin:0">This browser session stays signed in until you close it.</p></form></section>`;
}

async function flushOfflineChanges({ refreshAfter = false } = {}) {
  if (isAdmin || typeof AlignOffline === 'undefined') return;
  const result = await AlignOffline.flush(rawApi);
  const pending = await AlignOffline.pendingCount();
  if (result.flushed) {
    setConnectionStatus(pending ? 'offline' : (offlineRuntime.ready ? 'ready' : 'online'), pending);
    if (refreshAfter) await refresh();
    toast(`${result.flushed} offline change${result.flushed === 1 ? '' : 's'} synced.`);
  } else if (result.blocked) {
    setConnectionStatus('offline', pending);
    toast(`A saved offline change needs attention: ${result.error.message}`);
  }
}


function isExpectedServiceWorkerController() {
  const scriptUrl = navigator.serviceWorker?.controller?.scriptURL || '';
  return scriptUrl.includes(`service-worker.js?v=${ASSET_VERSION}`);
}

function waitForServiceWorkerController(timeoutMs = 8000) {
  if (isExpectedServiceWorkerController()) return Promise.resolve(true);
  return new Promise(resolve => {
    let settled = false;
    const finish = value => {
      if (settled) return;
      settled = true;
      navigator.serviceWorker?.removeEventListener('controllerchange', changed);
      resolve(value);
    };
    const changed = () => {
      if (isExpectedServiceWorkerController()) finish(true);
    };
    navigator.serviceWorker?.addEventListener('controllerchange', changed);
    window.setTimeout(() => finish(isExpectedServiceWorkerController()), timeoutMs);
  });
}

function workerState(registration) {
  if (!registration) return 'none';
  if (registration.installing) return `installing:${registration.installing.state}`;
  if (registration.waiting) return `waiting:${registration.waiting.state}`;
  if (registration.active) return `active:${registration.active.state}`;
  return 'registered:no-worker';
}

async function serviceWorkerReadyWithTimeout(timeoutMs = 10000) {
  return Promise.race([
    navigator.serviceWorker.ready,
    new Promise((_, reject) => window.setTimeout(() => reject(new Error('Timed out waiting for the service worker to activate.')), timeoutMs)),
  ]);
}

async function prepareOfflineRuntime() {
  if (isAdmin || !('serviceWorker' in navigator)) {
    offlineRuntime.registrationError = 'This browser does not expose the Service Worker API.';
    return false;
  }
  if (!window.isSecureContext) {
    offlineRuntime.registrationError = 'Safari does not regard this page as a secure context. Check the Align root certificate is installed and fully trusted.';
    return false;
  }
  if (offlineRuntime.preparing) return Boolean(navigator.serviceWorker.controller);
  offlineRuntime.preparing = true;
  offlineRuntime.registrationError = '';
  setConnectionStatus('caching');
  try {
    const registration = await navigator.serviceWorker.register(`/service-worker.js?v=${ASSET_VERSION}`, { scope: '/', updateViaCache: 'none' });
    offlineRuntime.registration = registration;
    if (navigator.serviceWorker.controller && !offlineRuntime.updateWatch) {
      offlineRuntime.updateWatch = true;
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (document.getElementById('align-update-ready')) return;
        const note = document.createElement('div');
        note.id = 'align-update-ready';
        note.setAttribute('role', 'status');
        note.style.cssText = 'position:fixed;left:12px;right:12px;bottom:12px;z-index:9999;padding:12px 14px;border-radius:12px;background:#17324d;color:#fff;display:flex;gap:12px;align-items:center;justify-content:space-between';
        note.innerHTML = '<span>A new version of Align is ready.</span><button type="button" style="min-height:44px;border-radius:8px;border:0;padding:0 14px">Refresh</button>';
        note.querySelector('button').addEventListener('click', () => window.location.reload());
        document.body.appendChild(note);
      });
    }
    offlineRuntime.registrationState = workerState(registration);

    const watched = registration.installing || registration.waiting || registration.active;
    if (watched) watched.addEventListener('statechange', () => { offlineRuntime.registrationState = workerState(registration); });
    if (registration.waiting) registration.waiting.postMessage({ type: 'ALIGN_SKIP_WAITING' });

    try { await registration.update(); } catch (_) {}
    await serviceWorkerReadyWithTimeout();
    offlineRuntime.registrationState = workerState(registration);
    const controlled = await waitForServiceWorkerController();

    // Some iOS/WebKit versions activate the worker but do not attach it to the
    // already-open standalone window until the next navigation. Reload once,
    // automatically, then stop so there can never be a reload loop.
    if (!controlled && registration.active && !sessionStorage.getItem('align-sw-control-reload-129')) {
      sessionStorage.setItem('align-sw-control-reload-129', '1');
      offlineRuntime.reloadingForControl = true;
      offlineRuntime.registrationError = 'Offline setup is ready. Reopen Align to finish enabling offline control.';
      return false;
    }
    if (isExpectedServiceWorkerController()) sessionStorage.removeItem('align-sw-control-reload-129');
    return isExpectedServiceWorkerController();
  } catch (error) {
    offlineRuntime.registrationError = String(error?.name ? `${error.name}: ${error.message || error}` : error?.message || error);
    offlineRuntime.registrationState = workerState(offlineRuntime.registration);
    return false;
  } finally {
    offlineRuntime.preparing = false;
  }
}

function requiredOfflineKeys() {
  return [`/api/bootstrap`, `/api/sections/definitions`];
}

async function requestWorkerDiagnostics() {
  const controller = navigator.serviceWorker?.controller;
  if (!controller) return { build: null, shellReady: false, shellMissing: [], apiUrls: [], error: 'No active service worker is controlling this screen.' };
  return new Promise(resolve => {
    const channel = new MessageChannel();
    const timer = window.setTimeout(() => resolve({ build: null, shellReady: false, shellMissing: [], apiUrls: [], error: 'Service worker diagnostic check timed out.' }), 3000);
    channel.port1.onmessage = event => {
      window.clearTimeout(timer);
      resolve(event.data || {});
    };
    controller.postMessage({ type: 'ALIGN_DIAGNOSTICS' }, [channel.port2]);
  });
}

function pathFromUrl(value) {
  try { const url = new URL(value, window.location.origin); return `${url.pathname}${url.search}`; }
  catch (_) { return String(value || ''); }
}

async function primeOfflineData() {
  if (isAdmin || typeof AlignOffline === 'undefined') return;
  const keys = requiredOfflineKeys();
  for (const path of keys) {
    try {
      const payload = await rawApi(path);
      await AlignOffline.remember(path, payload);
    } catch (_) {
      // Verification below will identify exactly which item is missing.
    }
  }
}

async function evaluateOfflineReadiness() {
  if (isAdmin) return { ready: false };
  const required = requiredOfflineKeys();
  const store = typeof AlignOffline !== 'undefined'
    ? await AlignOffline.diagnostics(required)
    : { indexedDb: false, cachedKeys: [], required: required.map(key => ({ key, ready: false })), pending: 0, error: 'offline-store.js did not load.' };
  const worker = await requestWorkerDiagnostics();
  const workerPaths = (worker.apiUrls || []).map(pathFromUrl);
  const apiRequired = required.map(key => ({ key, ready: workerPaths.includes(key) }));
  const ready = location.protocol === 'https:'
    && Boolean(navigator.serviceWorker?.controller)
    && worker.build === BUILD_VERSION
    && worker.shellReady === true
    && store.indexedDb === true
    && store.required.every(item => item.ready)
    && apiRequired.every(item => item.ready);
  const result = {
    ready,
    https: location.protocol === 'https:',
    secureContext: window.isSecureContext === true,
    serviceWorkerSupported: 'serviceWorker' in navigator,
    controller: isExpectedServiceWorkerController(),
    controllerScript: navigator.serviceWorker?.controller?.scriptURL || '',
    registrationError: offlineRuntime.registrationError,
    registrationState: offlineRuntime.registrationState || workerState(offlineRuntime.registration),
    worker,
    store,
    apiRequired,
  };
  offlineRuntime.ready = ready;
  offlineRuntime.diagnostics = result;
  return result;
}

async function completeOfflineSetup({ showResult = false } = {}) {
  if (isAdmin) return false;
  setConnectionStatus('caching', typeof AlignOffline !== 'undefined' ? await AlignOffline.pendingCount().catch(() => 0) : 0);
  await prepareOfflineRuntime();
  await primeOfflineData();
  const result = await evaluateOfflineReadiness();
  const pending = result.store?.pending || 0;
  if (!navigator.onLine) setConnectionStatus('offline', pending);
  else setConnectionStatus(result.ready ? 'ready' : 'warning', pending);
  if (showResult) await showOfflineDiagnostics();
  return result.ready;
}

function diagnosticRow(label, ok, detail = '') {
  return `<div class="offline-check ${ok ? 'ok' : 'bad'}"><span class="offline-check-icon">${ok ? '✓' : '!'}</span><div><strong>${escapeHtml(label)}</strong>${detail ? `<small>${escapeHtml(detail)}</small>` : ''}</div></div>`;
}

async function showOfflineDiagnostics() {
  const result = offlineRuntime.diagnostics || await evaluateOfflineReadiness();
  const required = result.store?.required || [];
  const apiRequired = result.apiRequired || [];
  const rows = [
    diagnosticRow('HTTPS', result.https && result.secureContext, result.secureContext ? 'Safari recognises this HTTPS connection as secure.' : (result.https ? 'The address uses HTTPS, but Safari does not regard the certificate as a secure context.' : 'Open Align using its https:// address.')),
    diagnosticRow('Service worker API', result.serviceWorkerSupported, result.serviceWorkerSupported ? 'Service workers are available in this browser.' : 'Safari is not exposing service workers for this page.'),
    diagnosticRow('Service worker registration', !result.registrationError, result.registrationError || `State: ${result.registrationState || 'unknown'}`),
    diagnosticRow('Service worker control', result.controller && result.worker?.build === BUILD_VERSION, result.controller ? `Build ${result.worker?.build || '?'} is controlling Align.` : `Build ${BUILD_VERSION} is not controlling this screen yet. Current controller: ${result.controllerScript || 'none'}. Registration state: ${result.registrationState || 'unknown'}.`),
    diagnosticRow('App shell cache', result.worker?.shellReady === true, result.worker?.shellReady ? 'The files needed to open Align are stored on this phone.' : `Missing: ${(result.worker?.shellMissing || []).join(', ') || (result.worker?.installFailures || []).map(item => `${item.asset}: ${item.error}`).join('; ') || result.worker?.error || 'worker not active yet'}`),
    diagnosticRow('Phone database', result.store?.indexedDb === true, result.store?.indexedDb ? 'IndexedDB is available.' : result.store?.error || 'IndexedDB is unavailable.'),
    ...required.map(item => diagnosticRow(`Local data · ${item.key.replace('/api/', '')}`, item.ready, item.ready ? 'Saved in the phone database.' : 'Not saved yet.')),
    ...apiRequired.map(item => diagnosticRow(`Offline response · ${item.key.replace('/api/', '')}`, item.ready, item.ready ? 'Saved in the service-worker cache.' : 'Not cached by the service worker yet.')),
  ].join('');
  modal('Offline status', `<div class="offline-diagnostics"><p class="helper">Build ${BUILD_VERSION} checks every layer instead of guessing. All checks must pass before Align says <strong>Offline Ready</strong>.</p>${rows}<div class="modal-actions"><button type="button" class="secondary-button" data-action="close-modal">Close</button><button type="button" class="primary-button" data-action="retry-offline-setup">Retry setup</button></div></div>`);
}

async function start() {
  const masterNav = document.querySelector('[data-nav="master"]');
  if (!isAdmin && masterNav) masterNav.remove();
  document.querySelector('.tab-bar').style.gridTemplateColumns = `repeat(${document.querySelectorAll('[data-nav]').length}, 1fr)`;
  if (isAdmin) {
    try {
      const status = await api('/api/admin/status');
      if (status.password_required && !status.authenticated) { renderAdminLogin(); return; }
    } catch (error) { renderAdminLogin(error.message); return; }
  }
  if (!isAdmin && typeof AlignOffline !== 'undefined') await flushOfflineChanges();
  await refresh();
  if (!isAdmin) void prepareOfflineRuntime().then(() => completeOfflineSetup()).catch(error => console.warn('Offline setup:', error));
}

const connectionStatusButton = document.querySelector('#connection-status');
if (connectionStatusButton) {
  connectionStatusButton.addEventListener('click', event => {
    event.preventDefault();
    event.stopPropagation();
    void showOfflineDiagnostics();
  });
}

window.addEventListener('online', () => { if (!isAdmin) void (async () => { await flushOfflineChanges({ refreshAfter: true }); await completeOfflineSetup(); })(); });
window.addEventListener('offline', async () => { if (!isAdmin && typeof AlignOffline !== 'undefined') setConnectionStatus('offline', await AlignOffline.pendingCount()); });
window.addEventListener('focus', () => { if (!isAdmin) void flushOfflineChanges({ refreshAfter: true }); });
document.addEventListener('visibilitychange', () => { if (!document.hidden && !isAdmin) void flushOfflineChanges({ refreshAfter: true }); });

start().catch(error => { app.innerHTML = `<div class="card empty form-error" role="alert">Unable to load Align: ${escapeHtml(error.message)}</div>`; });

let alignInstallPrompt = null;
function hideInstallButton() {
  const button = document.querySelector('#install-button');
  if (button) button.hidden = true;
}
async function promptAlignInstall() {
  if (!alignInstallPrompt) {
    toast('To install, use the browser menu. On iPhone, tap Share, then Add to Home Screen.');
    return;
  }
  try {
    await alignInstallPrompt.prompt();
    const choice = await alignInstallPrompt.userChoice;
    alignInstallPrompt = null;
    hideInstallButton();
    toast(choice?.outcome === 'accepted' ? 'Align will open from your home screen.' : 'Install was dismissed. You can try again from More.');
  } catch (error) {
    toast(error.message || 'Align could not open the install prompt.', 'error');
  }
}
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault();
  alignInstallPrompt = event;
  const button = document.querySelector('#install-button');
  if (button) button.hidden = false;
});
document.querySelector('#install-button')?.addEventListener('click', () => { void promptAlignInstall(); });
window.addEventListener('appinstalled', () => { alignInstallPrompt = null; hideInstallButton(); });

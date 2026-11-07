const fs = require('fs');
const vm = require('vm');

function scriptSources(html) {
  return [...html.matchAll(/<script\s+src="([^"]+)"/g)].map(match => match[1]);
}

function pathname(src) {
  return src.split('?')[0];
}

function assertUnique(label, sources) {
  const seen = new Map();
  for (const src of sources) {
    const path = pathname(src);
    if (seen.has(path)) {
      throw new Error(`${label} loads ${path} twice (${seen.get(path)} and ${src}). A second classic script redeclares top-level let/const, and iPhone Safari then reports "Can't find variable" for functions from that file.`);
    }
    seen.set(path, src);
  }
}

const index = fs.readFileSync('static/index.html', 'utf8');
const studio = fs.readFileSync('static/management-studio.html', 'utf8');
const appSource = fs.readFileSync('static/app.js', 'utf8');
const worker = fs.readFileSync('static/service-worker.js', 'utf8');
const build = appSource.match(/const BUILD_VERSION = (\d+);/);
const version = appSource.match(/const ASSET_VERSION = `\$\{BUILD_VERSION\}-([^`]+)`/);
if (!build || !version) throw new Error('Build and ASSET_VERSION templates are missing from app.js');
const assetVersion = `${build[1]}-${version[1]}`;

const plannerScripts = scriptSources(index);
const studioScripts = scriptSources(studio);
assertUnique('index.html', plannerScripts);
assertUnique('management-studio.html', studioScripts);

const plannerPaths = plannerScripts.map(pathname);
const beforeApp = new Set(plannerPaths.slice(0, plannerPaths.indexOf('/app.js')));
for (const required of ['/dates.js', '/work-setup.js', '/shift-planner.js', '/work-rota.js', '/personal-planner.js', '/travel-assets.js', '/builder-runtime.js', '/icloud.js']) {
  if (!beforeApp.has(required)) throw new Error(`${required} must load before app.js`);
}
if (!plannerPaths.includes('/build152.js') || plannerPaths.indexOf('/build152.js') < plannerPaths.indexOf('/app.js')) {
  throw new Error('build152.js must load after app.js');
}
for (const src of plannerScripts) {
  if (!src.endsWith(`?v=${assetVersion}`)) throw new Error(`${src} is not cached at ${assetVersion}`);
}
for (const path of plannerPaths) {
  if (!worker.includes(`\`${path}?v=\${ASSET_VERSION}\``) && !worker.includes(`${path}?v=\${ASSET_VERSION}`)) {
    throw new Error(`${path} is loaded by the planner but missing from the service worker shell`);
  }
}

function element(key, elements) {
  if (elements.has(key)) return elements.get(key);
  const node = {
    style: { setProperty() {}, getPropertyValue() { return ''; } },
    dataset: {},
    classList: {
      add() {},
      remove() {},
      toggle() { return false; },
      contains() { return false; },
    },
    hidden: false,
    disabled: false,
    open: false,
    textContent: '',
    innerHTML: '',
    value: '',
    id: String(key),
    title: '',
    loading: '',
    src: '',
    referrerPolicy: '',
    files: [],
    children: [],
    contentDocument: null,
    append() {},
    appendChild(child) { return child; },
    replaceChildren() {},
    remove() {},
    setAttribute() {},
    getAttribute() { return null; },
    removeAttribute() {},
    addEventListener() {},
    removeEventListener() {},
    querySelector(selector) { return element(`${key} ${selector}`, elements); },
    querySelectorAll() { return []; },
    closest() { return node; },
    focus() {},
    click() {},
    insertBefore(child) { return child; },
    matches() { return false; },
    contains() { return false; },
  };
  elements.set(key, node);
  return node;
}

function pageSandbox() {
  const elements = new Map();
  const document = {
    readyState: 'complete',
    body: element('body', elements),
    documentElement: element('documentElement', elements),
    activeElement: null,
    querySelector(selector) { return element(selector, elements); },
    querySelectorAll() { return []; },
    getElementById(id) { return element(`#${id}`, elements); },
    addEventListener() {},
    removeEventListener() {},
    createElement() { return element(`created-${elements.size}`, elements); },
    createElementNS() { return element(`created-${elements.size}`, elements); },
  };
  const storage = () => {
    const values = new Map();
    return {
      getItem(key) { return values.has(key) ? values.get(key) : null; },
      setItem(key, value) { values.set(key, String(value)); },
      removeItem(key) { values.delete(key); },
      clear() { values.clear(); },
    };
  };
  const pending = () => new Promise(() => {});
  const sandbox = {
    console,
    URL,
    URLSearchParams,
    TextEncoder,
    TextDecoder,
    Uint8Array,
    btoa,
    atob,
    setTimeout(...args) {
      const timer = setTimeout(...args);
      if (typeof timer.unref === 'function') timer.unref();
      return timer;
    },
    clearTimeout,
    setInterval(...args) {
      const timer = setInterval(...args);
      if (typeof timer.unref === 'function') timer.unref();
      return timer;
    },
    clearInterval,
    queueMicrotask,
    structuredClone,
    crypto,
    Blob,
    CustomEvent,
    Event,
    FormData,
    alert() {},
    confirm() { return false; },
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() { return true; },
    MutationObserver: class {
      observe() {}
      disconnect() {}
    },
    requestAnimationFrame(callback) { return setTimeout(callback, 0); },
    cancelAnimationFrame(id) { clearTimeout(id); },
    fetch: pending,
    indexedDB: { open() { return {}; } },
    isSecureContext: true,
    navigator: { onLine: true, userAgent: 'AlignScriptTest', geolocation: null },
    location: {
      href: 'https://align.test/',
      origin: 'https://align.test',
      protocol: 'https:',
      host: 'align.test',
      hostname: 'align.test',
      port: '',
      pathname: '/',
      search: '',
      hash: '',
    },
    sessionStorage: storage(),
    localStorage: storage(),
    matchMedia() { return { matches: false, addEventListener() {}, removeEventListener() {} }; },
    document,
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;
  vm.createContext(sandbox);
  return sandbox;
}

function loadScripts(sandbox, sources, label) {
  const errors = [];
  for (const src of sources) {
    const file = `static${pathname(src)}`;
    if (!fs.existsSync(file)) {
      errors.push(`${label} references missing file ${file}`);
      continue;
    }
    try {
      vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox, { filename: file });
    } catch (error) {
      const kind = error instanceof ReferenceError || error?.name === 'ReferenceError' ? 'ReferenceError' : 'load error';
      errors.push(`${file} ${kind}: ${error.message}`);
    }
  }
  if (errors.length) throw new Error(errors.join('\n'));
}

function runPage(sandbox, code) {
  try {
    return vm.runInContext(code, sandbox, { filename: 'page-script-check.js' });
  } catch (error) {
    if (error instanceof ReferenceError || error?.name === 'ReferenceError') {
      throw new Error(`ReferenceError while rendering: ${error.message}`);
    }
    throw error;
  }
}

const planner = pageSandbox();
loadScripts(planner, plannerScripts, 'planner');
const defined = runPage(planner, `({
  renderWorkSetup: typeof renderWorkSetup,
  renderWorkRota: typeof renderWorkRota,
  renderAssets150: typeof renderAssets150,
  renderTravel150: typeof renderTravel150,
  renderShiftPlanner: typeof renderShiftPlanner,
  personalToday: typeof personalToday,
  renderICloud: typeof renderICloud,
  builderStartup: typeof builderStartup,
  builderRecordsPage: typeof builderRecordsPage,
  formatDisplayDate: typeof formatDisplayDate,
})`);
for (const [name, kind] of Object.entries(defined)) {
  if (kind !== 'function') throw new Error(`${name} is ${kind} after the planner scripts load`);
}

runPage(planner, `
  state.boot = {
    build_version: 156,
    settings: { onboarding_completed: true, user_name: 'Alex', user_address: '', notifications: false },
    dashboard: { today: '2026-11-03', upcoming_events: [], alerts: [] },
    sections: [],
    calendar: { alert_rules: [], feed_path: '/api/calendars/align.ics' },
    personal: { items: [], events: [], today: '2026-11-03', preferences: { weather_town: '', include_overdue: false, show_todos: false } },
    builder: {
      document: {
        navigation: [],
        home_sections: [],
        formatting: {},
        base_structure: { weather: { enabled: false } },
      },
    },
  };
  state.sectionDefinitions = [];
  const screens = {
    today: 'Everything in one place',
    inbox: 'Inbox',
    sections: 'Set up Work Calendar',
    more: 'Work settings',
    planner: 'Planner',
    transport: 'Travel',
    assets: 'Asset Studio',
    'work-rota': 'Upload my rota',
  };
  const missing = [];
  for (const [tab, needle] of Object.entries(screens)) {
    state.tab = tab;
    if (tab === 'settings') state.settingsBranch = 'work';
    render();
    const html = document.querySelector('#app').innerHTML;
    if (html.includes('Unable to load Align') || html.includes("Can't find variable")) missing.push(tab + ' showed the load error');
    else if (!html.includes(needle)) missing.push(tab + ' did not render ' + needle);
  }
  state.tab = 'settings';
  state.settingsBranch = 'work';
  render();
  if (!document.querySelector('#app').innerHTML.includes('Work Settings')) missing.push('settings did not render Work Settings');
  state.settingsBranch = 'colours';
  state.boot.sections = [];
  render();
  const emptyColours = document.querySelector('#app').innerHTML;
  if (emptyColours.includes('is not defined') || emptyColours.includes('Unable to load Align') || !emptyColours.includes('No personal calendars yet')) {
    missing.push('colours settings did not open an empty calendar list');
  }
  state.boot.sections = [{ id: 4, name: 'Appointments', icon: '📅', colour: '#0878F9', calendar_name: 'Home', active: 1, align_event_count: 2, imported_event_count: 0 }];
  render();
  const colours = document.querySelector('#app').innerHTML;
  if (!colours.includes('Appointments') || !colours.includes('type="color"') || !colours.includes('#0878F9') || !colours.includes('2 events use this colour')) {
    missing.push('colours settings did not show the calendar colour');
  }
  workSetup = {
    data: {
      locations: [], areas: [], slots: [], assignments: [],
      contracted_hours: 37.5, duration_minutes: 450, rate_of_pay: 15,
      leave_allowance_days: 25, leave_year_start: '01-01', minimum_rest_hours: 11,
    },
    editor: null, error: '', saving: false, returnTab: 'more', category: '',
  };
  state.tab = 'work-setup';
  render();
  const work = document.querySelector('#app').innerHTML;
  if (work.includes('Unable to load Align') || !work.includes('Work Settings')) missing.push('work-setup did not render');
  state.tab = 'missing-screen';
  render();
  if (!document.querySelector('#app').innerHTML.includes('Everything in one place')) missing.push('unknown tab did not fall back to home');
  if (missing.length) throw new Error(missing.join('; '));
  globalThis.renderWorkSetup = undefined;
  state.tab = 'work-setup';
  render();
  const safe = document.querySelector('#app').innerHTML;
  if (safe.includes('Unable to load Align') || safe.includes("Can't find variable") || safe.includes('is not defined')) {
    throw new Error('A missing renderWorkSetup still blanks the planner');
  }
  if (!safe.includes('still loading')) throw new Error('A missing renderWorkSetup did not show the safe screen');
  state.boot.icloud_event_calendars = [{id:'cal-home', name:'Home'}];
  state.boot.icloud_public = {connected:false, calendars:[]};
  state.boot.sections = [];
  openSectionGuide();
  const setup = document.querySelector('#app').innerHTML;
  if (!setup.includes('New section') || !setup.includes('Name and colour') || !setup.includes('Appointments')) missing.push('section guide did not open');
  guideScreen.draft.name = 'Appointments';
  guideScreen.step = 2;
  render();
  const calendarStep = document.querySelector('#app').innerHTML;
  if (!calendarStep.includes('Which calendar') || !calendarStep.includes('Keep this in Align only')) missing.push('calendar step missing');
  guideScreen.step = 3;
  render();
  const placesStep = document.querySelector('#app').innerHTML;
  if (!placesStep.includes('Named place') || !placesStep.includes('Location only')) missing.push('places step missing');
  guideScreen.step = 4;
  render();
  const alertsStep = document.querySelector('#app').innerHTML;
  if (!alertsStep.includes('Leave-by travel alert') || !alertsStep.includes('Reminder before the event')) missing.push('alerts step missing');
  state.sectionId = 4;
  state.sectionData = {id:4, name:'Appointments', icon:'📅', colour:'#0878F9', calendar_id:'cal-home', events:[], places:[{id:1,name:'GP',location:'1 High Street'}], labels:[{id:1,name:'Health'}], guide:{place_id:1,travel_minutes:45,travel_mode:'bus',travel_info:'Bus from home',leave_alert_minutes:60,reminder_minutes:30}};
  openEventGuide();
  const eventStep = document.querySelector('#app').innerHTML;
  if (!eventStep.includes('+ Event') || !eventStep.includes('Appointment') || !eventStep.includes('Add to Appointments')) missing.push('event guide did not open');
  guideScreen.step = 2;
  render();
  const details = document.querySelector('#app').innerHTML;
  if (!details.includes('1 High Street') || !details.includes('Leave-by travel alert') || !details.includes('value="45"')) missing.push('event details were not filled from the section');
  if (!details.includes('Filled in from this section') || !details.includes('GP')) missing.push('saved place was not offered on the event');
  guideScreen.draft.title = 'Check-up';
  guideScreen.draft.location = 'High';
  refreshPlaceSuggestions();
  const matched = document.querySelector('[data-guide-suggestions]').innerHTML;
  if (!matched.includes('GP') || !matched.includes('1 High Street')) missing.push('saved place autocomplete missed GP');
  guideScreen.draft.location = 'zzzz';
  refreshPlaceSuggestions();
  if (!document.querySelector('[data-guide-suggestions]').innerHTML.includes('No saved places match')) missing.push('autocomplete empty state missing');
  guideScreen.draft.title = '';
  guideScreen.step = 1;
  guideScreen.draft.event_type = 'Other';
  render();
  const custom = document.querySelector('#app').innerHTML;
  if (!custom.includes('Custom type') || !custom.includes('Type a short name below.')) missing.push('custom event type field missing');
  guideScreen.draft.custom_type = '';
  if (validateGuideStep() !== 'Type a name for this event type.') missing.push('blank custom type was accepted');
  guideScreen.kind = 'section';
  guideScreen.step = 1;
  guideScreen.draft.name = '   ';
  if (validateGuideStep() !== 'Give this section a name.') missing.push('blank section name was accepted');
  if (missing.length) throw new Error(missing.join('; '));
`);

const studioPage = pageSandbox();
loadScripts(studioPage, studioScripts, 'management studio');
const studioGlobals = runPage(studioPage, `({
  AlignFields: typeof AlignFields,
  AlignFormatting: typeof AlignFormatting,
  formatDisplayDate: typeof formatDisplayDate,
  AlignBuilderStudio: typeof AlignBuilderStudio,
  AlignManagementStudio: typeof AlignManagementStudio,
  AlignManagementStudioNav: typeof AlignManagementStudioNav,
  AlignStudioCalendar: typeof AlignStudioCalendar,
  AlignOwnerAdmin: typeof AlignOwnerAdmin,
})`);
for (const [name, kind] of Object.entries(studioGlobals)) {
  if (kind !== 'function' && kind !== 'object') throw new Error(`Management Studio ${name} is ${kind} after its scripts load`);
}

console.log('planner and Management Studio scripts load without ReferenceError');

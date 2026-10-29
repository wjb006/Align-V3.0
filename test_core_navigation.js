const fs = require('fs');
const app = fs.readFileSync('static/app.js', 'utf8');
const studio = fs.readFileSync('static/owner-builder.js', 'utf8');
const runtime = fs.readFileSync('static/builder-runtime.js', 'utf8');
const index = fs.readFileSync('static/index.html', 'utf8');
const worker = fs.readFileSync('static/service-worker.js', 'utf8');
const personal = fs.readFileSync('static/personal-planner.js', 'utf8');
const admin = fs.readFileSync('static/admin.html', 'utf8');
const widget = fs.readFileSync('static/align-widget.js', 'utf8');
const offline = fs.readFileSync('static/offline-store.js', 'utf8');

for (const label of ['Today', 'Inbox', 'Sections', 'More']) {
  if (!app.includes(`title:'${label}'`)) throw new Error(`Missing core navigation item: ${label}`);
}
for (const route of ['today: renderHome','inbox: renderInbox','sections: renderSectionsIndex','more: renderMore']) {
  if (!app.includes(route)) throw new Error(`Missing core navigation route: ${route}`);
}
if (!app.includes('planner: renderPlannerCalendar')) throw new Error('Restored Planner route is missing');
if (app.includes("if (['calendar','add','work-setup'].includes(state.tab))") || app.includes("if (['calendar','add'].includes(state.tab))")) throw new Error('Planner destinations must not be redirected to Sections');
if (!app.includes('Work (optional)')) throw new Error('Optional Work section prompt is missing');
if (!app.includes("'/api/builder/records/work/enable'")) throw new Error('Work opt-in action is missing');
const more = app.slice(app.indexOf('function renderMore()'), app.indexOf('function rootParentBranches()'));
if (more.includes('Asset Studio') || more.includes("data-nav=\"assets\"")) throw new Error('Owner Asset Studio controls must stay in Align Management Studio, outside the user app');
const settings = app.slice(app.indexOf('function renderUserSettings()'), app.indexOf('function renderUserBranch('));
if (settings.includes('Asset Studio') || settings.includes('Management Studio')) throw new Error('Owner management controls must stay outside user settings');
for (const role of ['location','area','date','start_time','end_time']) {
  if (!studio.includes(`'${role}'`)) throw new Error(`Work field association ${role} is missing from Studio`);
}
if (!runtime.includes('const work = (state.sectionDefinitions || []).find')) throw new Error('Opening Work from its Studio menu should activate per-user opt-in');
if (!app.includes('class="inbox-item-text"')) throw new Error('Inbox full note text layout missing');
const onboarding = app.slice(app.indexOf('function renderOnboarding()'), app.indexOf('function renderLocalDataSettings()'));
if (/Shift notifications|Continue to Work Settings|Default calendar/.test(onboarding)) throw new Error('First-run setup still contains fixed shift/work-schedule fields');
if (!onboarding.includes('Work as an optional database in Sections')) throw new Error('First-run setup does not explain optional Work setup');
if (app.includes("state.boot.master") || app.includes("api('/api/master')")) throw new Error('Legacy Master payload must not be used by V3');
if (!app.includes('state.boot.navigation?.parents')) throw new Error('Section folder choices must use the retained V3 navigation payload');
if (!app.includes('/api/alert-rules') || !app.includes('function alertRuleModal')) throw new Error('Restored planner alert settings are missing');
if (!app.includes("branch_key: 'work'")) throw new Error('Work Settings branch is missing');
if (!app.includes("branch_key: 'alerts'")) throw new Error('Planner alert settings branch is missing');
const shiftPlanner = fs.readFileSync('static/shift-planner.js', 'utf8');
if (!shiftPlanner.includes('data-shift-action="list"') || !shiftPlanner.includes('renderMonthList')) throw new Error('Planner list view is missing');
if (!shiftPlanner.includes('imported_events') || !shiftPlanner.includes('restGapWarnings')) throw new Error('Planner event integration or rest-gap warnings are missing');
if (!shiftPlanner.includes('data-shift-action="edit-event"')) throw new Error('Direct Planner event editing is missing');
if (!app.includes("branch_key: 'events'")) throw new Error('Events and calendar settings branch is missing');
if (personal.includes('regular_work')) throw new Error('Legacy regular-work shift-pattern preference must be retired');
if (!admin.includes('/management-studio.html')) throw new Error('Legacy Admin entrypoint must lead to Management Studio');
if (widget.includes('/api/shifts')) throw new Error('Scriptable widget must use the retained V3 event feed');
if (!widget.includes("b.dashboard?.upcoming_events")) throw new Error('Scriptable widget must read V3 dashboard events');
if (offline.includes('queueShiftBatch')) throw new Error('New offline writes must not queue retired shift batches');
if (!offline.includes("if (item.kind === 'shift-batch') continue;")) throw new Error('Legacy offline shift batches must be retained without replay');
if (widget.includes('NEXT SHIFT')) throw new Error('Scriptable widget must not label events as shifts');
if (!fs.existsSync('static/shift-planner.js')) throw new Error('Restored shift planner client is missing');
if (!fs.existsSync('static/work-setup.js')) throw new Error('Restored Work Settings client is missing');
if (offline.includes('pendingShifts(') || offline.includes("path: '/api/shifts'")) throw new Error('Offline V3 must not construct or overlay retired shift records');
if (worker.includes("url.pathname === '/api/week'")) throw new Error('Retired week endpoint must not be cached as an offline-safe API');
if (!app.includes("{ branch_key: 'events', title: 'Events & calendars'")) throw new Error('Account Settings is missing Events and calendar controls');
for (const [name, source] of [['app',app],['index',index],['service worker',worker]]) {
  if (source.includes('maps173')) throw new Error(`Stale maps173 asset version remains in ${name}`);
}
if (!app.includes('const ASSET_VERSION = `${BUILD_VERSION}-v57`;')) throw new Error('App asset version template is not the current Build 156 assets');
if (!index.includes('156-v58')) throw new Error('Index asset version is not 156-v58');
if (!worker.includes('align-v13-shell-${ASSET_VERSION}')) throw new Error('Shell cache template is missing');
if (!worker.includes('align-v13-api-${ASSET_VERSION}')) throw new Error('API cache template is missing');
if (!worker.includes("url.pathname === '/api/sections/definitions'")) throw new Error('Offline-safe API cache omits section definitions');
if (!app.includes('const addressSearchTimers = new WeakMap();')) throw new Error('Address suggestions are missing their debounce timer store');
if (!app.includes('data-address-search="true"')) throw new Error('Address fields do not support live suggestions');
if (!index.includes('/work-setup.js?v=156-v58') || !worker.includes('/work-setup.js?v=${ASSET_VERSION}')) throw new Error('Restored Work Settings assets are not loaded and cached');
console.log('core navigation, Events, Work Settings and Planner settings checks passed');

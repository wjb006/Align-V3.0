const fs = require('fs');
const app = fs.readFileSync('static/app.js', 'utf8');
const studio = fs.readFileSync('static/owner-builder.js', 'utf8');
const runtime = fs.readFileSync('static/builder-runtime.js', 'utf8');
const index = fs.readFileSync('static/index.html', 'utf8');
const worker = fs.readFileSync('static/service-worker.js', 'utf8');

for (const label of ['Today', 'Inbox', 'Sections', 'More']) {
  if (!app.includes(`title:'${label}'`)) throw new Error(`Missing core navigation item: ${label}`);
}
for (const route of ['today: renderHome','inbox: renderInbox','sections: renderSectionsIndex','more: renderMore']) {
  if (!app.includes(route)) throw new Error(`Missing core navigation route: ${route}`);
}
if (app.includes("title:'Planner'")) throw new Error('Legacy Planner should not be a core navigation item');
if (!app.includes("['planner','calendar','add']")) throw new Error('Legacy planner links must continue routing to Sections');
if (!app.includes('Work (optional)')) throw new Error('Optional Work section prompt is missing');
if (!app.includes("'/api/builder/records/work/enable'")) throw new Error('Work opt-in action is missing');
for (const role of ['location','area','date','start_time','end_time']) {
  if (!studio.includes(`'${role}'`)) throw new Error(`Work field association ${role} is missing from Studio`);
}
if (!runtime.includes('const work = (state.sectionDefinitions || []).find')) throw new Error('Opening Work from its Studio menu should activate per-user opt-in');
if (!app.includes('class="inbox-item-text"')) throw new Error('Inbox full note text layout missing');
const onboarding = app.slice(app.indexOf('function renderOnboarding()'), app.indexOf('function renderLocalDataSettings()'));
if (/Shift notifications|Continue to Work Settings|Default calendar/.test(onboarding)) throw new Error('First-run setup still contains fixed shift/work-schedule fields');
if (!onboarding.includes('Work as an optional database in Sections')) throw new Error('First-run setup does not explain optional Work setup');
if (!app.includes("{ branch_key: 'calendar', title: 'Calendar'")) throw new Error('Account Settings is missing calendar controls');
for (const [name, source] of [['app',app],['index',index],['service worker',worker]]) {
  if (source.includes('maps173')) throw new Error(`Stale maps173 asset version remains in ${name}`);
}
if (!app.includes('const ASSET_VERSION = `${BUILD_VERSION}-v35`;')) throw new Error('App asset version template is not the current Build 156 assets');
if (!index.includes('156-v35')) throw new Error('Index asset version is not 156-v35');
if (!worker.includes('align-v13-shell-${ASSET_VERSION}')) throw new Error('Shell cache template is missing');
if (!worker.includes('align-v13-api-${ASSET_VERSION}')) throw new Error('API cache template is missing');
console.log('core navigation and optional Work setup checks passed');

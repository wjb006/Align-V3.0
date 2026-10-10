const fs = require('fs');

const app = fs.readFileSync('static/app.js', 'utf8');
const week = fs.readFileSync('static/week-planner.js', 'utf8');
const month = fs.readFileSync('static/month-calendar.js', 'utf8');
const workSetup = fs.readFileSync('static/work-setup.js', 'utf8');
const index = fs.readFileSync('static/index.html', 'utf8');
const worker = fs.readFileSync('static/service-worker.js', 'utf8');

for (const label of ['Today', 'Inbox', 'Planner', 'Sections', 'More']) {
  if (!app.includes(`title:'${label}'`)) throw new Error(`Missing core navigation item: ${label}`);
}

for (const route of [
  'today: renderHome',
  'inbox: renderInbox',
  'planner: renderCalendar',
  'sections: renderSectionsIndex',
  'more: renderMore',
]) {
  if (!app.includes(route)) throw new Error(`Missing core navigation route: ${route}`);
}

if (!app.includes("['planner','calendar','add']")) throw new Error('Planner compatibility mapping missing');
if (!app.includes("['sections','section']")) throw new Error('Sections compatibility mapping missing');
if (!week.includes('<h1>Planner</h1>')) throw new Error('Planner heading missing');
if (!week.includes("['calendar','planner'].includes(state.tab)")) throw new Error('Planner async refresh compatibility missing');
if (!month.includes("['calendar','planner'].includes(state.tab)")) throw new Error('Planner month async refresh compatibility missing');
if (!month.includes('<h1>Planner</h1>')) throw new Error('Planner month heading missing');
if (!app.includes("state.tab = 'sections'; await refresh(); toast('Section deleted.');")) throw new Error('Section delete does not return to Sections');
if (!app.includes('class="inbox-item-text"')) throw new Error('Inbox full note text layout missing');
if (!workSetup.includes("returnTab: state.tab")) throw new Error('Work setup does not remember entry screen');
if (!workSetup.includes("workSetup.returnTab==='more'?'More'")) throw new Error('Work setup back label does not support More');

for (const [name, source] of [['app', app], ['index', index], ['service worker', worker]]) {
  if (source.includes('maps173')) throw new Error(`Stale maps173 asset version remains in ${name}`);
}

if (!app.includes('const ASSET_VERSION = `${BUILD_VERSION}-v32`;')) throw new Error('App asset version template is not the current Build 156 assets');
if (!index.includes('156-v32')) throw new Error('Index asset version is not 156-v32');
if (!worker.includes('align-v13-shell-${ASSET_VERSION}')) throw new Error('Shell cache template is missing');
if (!worker.includes('align-v13-api-${ASSET_VERSION}')) throw new Error('API cache template is missing');

console.log('core navigation checks passed');

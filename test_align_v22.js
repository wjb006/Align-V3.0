const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const app = fs.readFileSync('static/app.js', 'utf8');
const planner = fs.readFileSync('static/personal-planner.js', 'utf8');
const week = fs.readFileSync('static/week-planner.js', 'utf8');
const list = fs.readFileSync('static/build152.js', 'utf8');
const studio = fs.readFileSync('static/management-studio.js', 'utf8');
const css = fs.readFileSync('static/styles.css', 'utf8');
const post = fs.readFileSync('static/post-event-travel.js', 'utf8');

assert.match(app, /function renderHomeGreeting/);
assert.match(app, /function fullDateLabel/);
assert.match(app, /function dayHeading/);
assert.match(app, /function locationSearchField/);
assert.match(app, /function renderEventRow/);
assert.match(app, /home-greeting/);
assert.doesNotMatch(app, /function renderNextStep/);
assert.match(planner, /condensed:\s*true/);
assert.match(planner, /showLocation:\s*false/);
assert.match(week, /dayHeading\(day\)/);
assert.match(list, /dayHeading\(date\)/);
assert.match(studio, /Home areas/);
assert.match(studio, /data-home-content/);
assert.match(studio, /show_schedule/);
assert.match(css, /\.event-condensed/);
assert.match(css, /--section-colour/);
assert.match(post, /function eventIsUnderway/);
assert.match(post, /function eventTravelMarkup/);

const context = {
  document: { addEventListener() {} },
  setInterval() {},
  personalPrefs: () => ({ default_travel: 'transit' }),
  escapeHtml: s => String(s ?? ''),
  travelCard: notes => notes ? `<details class="compact-event-details"><summary>Journey</summary>${notes}</details>` : '',
  savedTravelSummary: () => '',
  Date,
  Intl,
};
vm.createContext(context);
vm.runInContext(post, context);

const futureStart = new Date(Date.now() + 60 * 60 * 1000).toISOString();
const futureEnd = new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString();
const pastStart = new Date(Date.now() - 60 * 60 * 1000).toISOString();
const soonEnd = new Date(Date.now() + 30 * 60 * 1000).toISOString();

assert.equal(context.eventIsUnderway({ start_at: futureStart, end_at: futureEnd }), false);
assert.equal(context.eventIsUnderway({ start_at: pastStart, end_at: soonEnd }), true);
assert.match(context.eventTravelMarkup({ start_at: futureStart, end_at: futureEnd, notes: 'walk' }), /Journey/);
assert.equal(context.eventTravelMarkup({ start_at: pastStart, end_at: soonEnd, notes: 'walk' }), '');

// Wall-clock London times without a Z suffix must still detect "under way".
const londonNow = new Date().toLocaleString('en-GB', { timeZone: 'Europe/London', hourCycle: 'h23' });
const [day, month, year] = londonNow.split(',')[0].split('/').map(Number);
const [hour, minute] = londonNow.split(', ')[1].split(':').map(Number);
const pad = n => String(n).padStart(2, '0');
const wall = `${year}-${pad(month)}-${pad(day)}T${pad(hour)}:${pad(minute)}`;
const wallEndHour = (hour + 1) % 24;
const wallEnd = `${year}-${pad(month)}-${pad(day)}T${pad(wallEndHour)}:${pad(minute)}`;
assert.equal(context.eventIsUnderway({ start_at: wall, end_at: wallEnd, notes: 'walk' }), true);
assert.equal(context.eventTravelMarkup({ start_at: wall, end_at: wallEnd, notes: 'walk' }), '');

console.log('Align V2.2 UI checks passed');

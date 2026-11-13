const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const post = fs.readFileSync('static/post-event-travel.js', 'utf8');
const journey = fs.readFileSync('static/journey-breakdown.js', 'utf8');
const app = fs.readFileSync('static/app.js', 'utf8');
const start = app.indexOf('function homeScheduleItems(');
const end = app.indexOf('\nfunction renderHome(', start);
assert(start >= 0 && end > start);
const now = new Date();
now.setHours(12, 0, 0, 0);
const iso = date => date.toISOString();
const today = iso(now).slice(0, 10);
const finished = {title:'Clinic', start_at:iso(new Date(now.getTime() - 2 * 3600000)), end_at:iso(new Date(now.getTime() - 3600000))};
const nextToday = {title:'Dentist', start_at:iso(new Date(now.getTime() + 3600000)), end_at:iso(new Date(now.getTime() + 2 * 3600000))};
const tomorrow = new Date(now.getTime() + 24 * 3600000);
const later = {title:'Tomorrow visit', start_at:iso(tomorrow), end_at:iso(new Date(tomorrow.getTime() + 3600000))};
const context = {
  Date: class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : [now.getTime()])); }
    static now() { return now.getTime(); }
  },
  escapeHtml:value => String(value ?? ''),
  document:{addEventListener(){}},
  setInterval(){ return 0; },
  state:{boot:null, tab:'today'},
  modalRoot:{textContent:''},
};
vm.createContext(context);
vm.runInContext(journey + '\n' + post + '\n' + app.slice(start, end), context);

const sameDay = context.homeScheduleItems([finished, nextToday], today);
assert.equal([...sameDay.items].map(item => item.title).join('|'), 'Dentist');
assert.equal(sameDay.later, false);

const afterToday = context.homeScheduleItems([finished], today);
assert.equal(afterToday.items.length, 0);

const nextDay = context.homeScheduleItems([finished, later], today);
assert.equal(nextDay.later, true);
assert.equal(nextDay.items[0].title, 'Tomorrow visit');

const line = context.condensedJourneyText({
  leave_at:'2030-01-02T08:04', arrival_at:'2030-01-02T08:44',
  steps:[
    {mode:'walk', minutes:4},
    {mode:'bus', service:'414', minutes:20},
    {mode:'walk', minutes:5},
  ],
});
assert.equal(line, 'Leave 08:04 · Bus 414 · Arrive 08:44');
const summary = context.postTravelSummary({
  location:'Clinic',
  post_travel:{enabled:true, deadline:'2030-01-02T09:00', destination_name:'Home',
    journey:{leave_at:'2030-01-02T08:04', arrival_at:'2030-01-02T08:44', steps:[{mode:'bus', service:'414'}]}},
}, {condensed:true});
assert.match(summary, /travel-condensed/);
assert.match(summary, /Leave 08:04 · Bus 414 · Arrive 08:44/);
assert.doesNotMatch(summary, /journey-compact-item/);
console.log('Home keeps the next event and condenses travel');

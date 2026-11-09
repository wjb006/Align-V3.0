const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const app = fs.readFileSync('static/app.js', 'utf8');
const personal = fs.readFileSync('static/personal-planner.js', 'utf8');
const start = app.indexOf('function homeScheduleItems(');
const end = app.indexOf('\nfunction todayInboundKey(', start);
assert(start >= 0 && end > start);
const forecast = {
  place: 'Test town', checked_at: '2030-01-01T10:00:00Z', source: 'Open-Meteo',
  current: {time: '2030-01-01T10:00', weather_code: 3, temperature_2m: 12},
  daily: {time: ['2030-01-01', '2030-01-02'], weather_code: [3, 0],
    temperature_2m_min: [8, 7], temperature_2m_max: [13, 14]},
};
let requests = 0;
const context = {
  state: {tab: 'today', boot: {dashboard: {today: '2030-01-01', upcoming_events: []},
    personal: {preferences: {weather_town: 'Test town'}}}},
  navigator: {geolocation: {getCurrentPosition: success => success({coords: {latitude: 53, longitude: -3}})}},
  window: {isSecureContext: true, setTimeout: () => 1, clearTimeout() {}},
  document: {addEventListener() {}},
  setTimeout, clearTimeout, escapeHtml: value => String(value ?? ''), fullDateLabel: x => x,
  homeSection: () => true, homeSectionContent: () => true, todayTimelineItemCount: () => 0,
  ensureDailyTravel() {}, render() {}, formatDisplayDateTime: x => x, prettyDate: x => x,
  api: async () => { requests++; return forecast; },
};
vm.createContext(context);
vm.runInContext(personal + '\n' + app.slice(start, end), context);
(async () => {
  assert.match(context.renderHome(), /Getting weather/);
  await new Promise(resolve => setImmediate(resolve));
  const html = context.renderHome();
  assert.equal(requests, 1);
  assert.match(html, /Test town/);
  assert.match(html, /12°C/);
  assert.match(html, /7 days/);
  assert.match(html, /data-personal="weather"/);
  context.homeSectionContent = (_, key) => key !== 'show_weather';
  assert.doesNotMatch(context.renderHome(), /data-weather-result/);
  context.homeSectionContent = () => true;
  context.state.boot.builder = {document: {base_structure: {weather: {enabled: false}}}};
  assert.match(context.renderHome(), /Weather is disabled by the owner/);
  assert.equal(requests, 1);
  console.log('Today renders and loads the forecast');
})().catch(error => { console.error(error); process.exitCode = 1; });

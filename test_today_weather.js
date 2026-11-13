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
  hourly: {time: ['2030-01-01T10:00'], temperature_2m: [12], precipitation_probability: [20], weather_code: [3]},
  daily: {time: ['2030-01-01', '2030-01-02'], weather_code: [3, 0],
    temperature_2m_min: [8, 7], temperature_2m_max: [13, 14], precipitation_probability_max: [20, 10]},
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
  assert.match(html, /Rain /);
  assert.match(html, /High /);
  assert.match(html, /Low /);
  assert.match(html, /design-hour/);
  assert.match(html, /data-personal="weather"/);
  const chip = context.eventForecastChip('2030-01-01T10:00');
  assert.match(chip, /12°/);
  assert.match(chip, /rain 20%/);
  assert.equal(context.eventForecastChip('2030-01-01T11:00'), '', 'Hours missing from the forecast stay blank');
  context.homeSectionContent = (_, key) => key !== 'show_weather';
  assert.doesNotMatch(context.renderHome(), /data-weather-result/);
  context.homeSectionContent = () => true;
  context.state.boot.builder = {document: {base_structure: {weather: {enabled: false}}}};
  assert.match(context.renderHome(), /Weather is disabled by the owner/);
  assert.equal(requests, 1);
  console.log('Today renders and loads the forecast');
})().catch(error => { console.error(error); process.exitCode = 1; });

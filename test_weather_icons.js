const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const source = fs.readFileSync('static/personal-planner.js', 'utf8');
const start = source.indexOf('function weatherIsNight(');
const end = source.indexOf('function forecastAt(', start);
assert.ok(start >= 0 && end > start);
const context = { escapeHtml: value => String(value ?? '') };
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

const kind = (code, when, wind) => context.weatherKind(code, when, wind);
assert.equal(kind(0, '2030-06-01T10:00').file, 'clear-day');
assert.equal(kind(0, '2030-06-01T22:00').file, 'clear-night');
assert.equal(kind(1, '2030-06-01T05:00').label, 'Clear night');
assert.equal(kind(2, '2030-06-01T14:00').file, 'partly-day');
assert.equal(kind(2, '2030-06-01T21:00').file, 'partly-night');
assert.equal(kind(3, '2030-06-01T12:00').file, 'cloud');
assert.equal(kind(51, '2030-06-01T12:00').file, 'drizzle');
assert.equal(kind(63, '2030-06-01T12:00').file, 'rain');
assert.equal(kind(65, '2030-06-01T12:00').file, 'heavy-rain');
assert.equal(kind(95, '2030-06-01T12:00').file, 'thunder');
assert.equal(kind(73, '2030-06-01T12:00').file, 'snow');
assert.equal(kind(66, '2030-06-01T12:00').file, 'sleet');
assert.equal(kind(45, '2030-06-01T12:00').file, 'fog');
assert.equal(kind(1, '2030-06-01T12:00', 45).file, 'wind');
assert.equal(kind(63, '2030-06-01T12:00', 50).file, 'rain');

const art = context.weatherArt(2, '2030-06-01T15:00', 0, 'small');
assert.match(art, /src="\/weather\/partly-day\.svg"/);
assert.match(art, /alt="Partly cloudy"/);
assert.match(art, /weather-art-small/);
assert.doesNotMatch(art, /[\u2600-\u26FF\u{1F300}-\u{1F5FF}]/u);

for (const file of ['clear-day','clear-night','partly-day','partly-night','cloud','drizzle','rain','heavy-rain','thunder','snow','sleet','fog','wind']) {
  assert.ok(fs.existsSync(`static/weather/${file}.svg`), file);
}
const worker = fs.readFileSync('static/service-worker.js', 'utf8');
assert.match(worker, /\/weather\/clear-night\.svg/);
assert.match(worker, /\$\{BUILD\}-v101/);
console.log('PASS: weather icons map day, night and conditions');

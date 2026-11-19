const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..', 'static');

function day(offset) {
  const value = new Date();
  value.setDate(value.getDate() + offset);
  return value.toISOString().slice(0, 10);
}

function start() {
  const server = http.createServer((request, response) => {
    const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    const file = path.join(root, pathname === '/' ? 'index.html' : pathname);
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      response.writeHead(404); response.end('missing'); return;
    }
    response.writeHead(200); response.end(fs.readFileSync(file));
  });
  return new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(server)));
}

(async () => {
  const today = day(1);
  const boot = {
    build_version: 158,
    settings: { user_name: 'Alex', onboarding_completed: true },
    personal: { preferences: { weather_town: 'Test Town', default_travel: 'transit', departure_buffer: 5 }, items: [] },
    builder: { document: { navigation: [
      { id: 'today', title: 'Today', icon: '⌂', destination: 'today', active: true },
    ], home_sections: [{ id: 'today', visible: true, content: { show_weather: true, show_quick_add: true } }], formatting: {} } },
    dashboard: {
      today,
      summary: { week_hours: 24, shift_count: 3 },
      upcoming_events: [
        { id: 1, origin: 'Shift', location_name: 'Riverside Health Centre', location: '1 Example Lane, Test Town',
          start_at: `${today}T08:00`, end_at: `${today}T12:00`, hours: 4, work_date: today,
          shift_type_name: 'Wards', shift_type_colour: '#16d5d0', location_colour: '#078ef0' },
      ],
    },
    sections: [], navigation: { parents: [] },
    icloud_public: { connected: false, last_error: 'Sign-in needs renewing' },
    home_status: { leave_alerts_enabled: true },
    icloud_event_calendars: [],
  };
  const server = await start();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/bootstrap') return route.fulfill({ json: boot });
    if (pathname === '/api/sections/definitions') return route.fulfill({ json: { sections: [] } });
    if (pathname === '/api/personal/weather') return route.fulfill({ json: {
      place: 'Test Town', current: { temperature_2m: 11, weather_code: 2, time: `${today}T08:00` },
      daily: { temperature_2m_max: [14], temperature_2m_min: [7], precipitation_probability_max: [20], weather_code: [2] },
      hourly: { time: [`${today}T08:00`], temperature_2m: [11], precipitation_probability: [20], weather_code: [2] },
    } });
    if (pathname === '/api/personal/journey') return route.fulfill({ json: {
      notes: 'Example journey from the provider',
      leave_at: `${today}T07:05`, arrival_at: `${today}T07:50`, steps: [
        { mode: 'walk', minutes: 6 }, { mode: 'bus', minutes: 28, service: '12' },
      ],
    } });
    return route.fulfill({ json: {} });
  });
  await page.goto('http://127.0.0.1:' + server.address().port + '/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.home-now-card');
  const card = await page.locator('.home-now-card').innerText();
  assert.match(card, /next|now/i);
  assert.match(card, /Wards/);
  assert.match(card, /In \d|Happening now|Starting now/);
  await page.waitForSelector('.home-leave');
  assert.match(await page.locator('.home-leave').innerText(), /Leave by 07:05/);
  assert.match(await page.locator('.home-week').innerText(), /This week · 3 shifts · 24h/);
  assert.match(await page.locator('.home-status').innerText(), /iCloud needs attention/);
  assert.match(await page.locator('.home-status').innerText(), /Leave alerts on/);
  assert.match(await page.locator('.design-weather').innerText(), /test town/i);
  const button = page.locator('.home-quick-add');
  const box = await button.boundingBox();
  assert.ok(box.height >= 44 && box.width >= 44, 'quick add tap target');
  const empty = await page.evaluate(() => {
    state.boot.dashboard.upcoming_events = [];
    render();
    return document.querySelector('.home-empty')?.innerText || '';
  });
  assert.match(empty, /Nothing coming up/);
  await browser.close();
  await new Promise(resolve => server.close(resolve));
  console.log('PASS: home now/next, week, status, weather and quick add');
})().catch(error => { console.error(error); process.exit(1); });

const { chromium, devices } = require('playwright');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..', 'static');

function start() {
  const server = http.createServer((request, response) => {
    const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    const file = path.join(root, pathname === '/' ? 'index.html' : pathname);
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      response.writeHead(404);
      response.end('missing');
      return;
    }
    response.writeHead(200);
    response.end(fs.readFileSync(file));
  });
  return new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(server)));
}

async function check(browser, deviceName) {
  const context = await browser.newContext({ ...devices[deviceName] });
  const page = await context.newPage();
  await page.goto(process.env.ALIGN_STATIC_URL + '/', { waitUntil: 'domcontentloaded' });
  const manifest = await page.locator('link[rel="manifest"]').getAttribute('href');
  assert.match(manifest, /manifest\.json/);
  assert.equal(await page.locator('meta[name="apple-mobile-web-app-capable"]').getAttribute('content'), 'yes');
  assert.equal(await page.locator('link[rel="apple-touch-icon"]').count(), 1);
  const splashes = await page.locator('link[rel="apple-touch-startup-image"]').count();
  assert.ok(splashes >= 3, deviceName + ' splash links');
  const install = page.locator('#install-button');
  await install.waitFor({ state: 'attached' });
  assert.equal(await install.getAttribute('aria-label'), 'Install Align');
  const bell = page.getByRole('link', { name: 'Phone notifications' });
  const bellBox = await bell.boundingBox();
  assert.ok(bellBox && bellBox.width >= 24 && bellBox.height >= 24, deviceName + ' notifications control');
  const manifestBody = await (await page.request.get(process.env.ALIGN_STATIC_URL + '/manifest.json')).json();
  assert.equal(manifestBody.display, 'standalone');
  assert.ok(manifestBody.icons.some(icon => icon.sizes === '192x192'));
  assert.ok(manifestBody.icons.some(icon => icon.purpose === 'maskable'));
  await page.goto(process.env.ALIGN_STATIC_URL + '/beta-login.html', { waitUntil: 'domcontentloaded' });
  await page.getByRole('link', { name: 'I have an invite' }).click();
  assert.match(page.url(), /invite/);
  await context.close();
}

(async () => {
  const server = await start();
  process.env.ALIGN_STATIC_URL = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch({ headless: true });
  try {
    await check(browser, 'iPhone 13');
    await check(browser, 'Pixel 7');
    console.log('PASS: install metadata on iPhone 13 and Pixel 7');
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

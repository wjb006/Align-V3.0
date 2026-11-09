const {chromium, webkit, devices} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, 'static', file), 'utf8');

(async () => {
  const browser = await (process.env.BROWSER === 'webkit' ? webkit : chromium).launch({headless:true});
  const context = await browser.newContext(process.env.MOBILE_DEVICE ? devices[process.env.MOBILE_DEVICE] : {});
  const page = await context.newPage();
  const requests = [];
  try {
    await page.clock.install();
    await page.route('http://address.test/**', route => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname === '/') return route.fulfill({contentType:'text/html', body:'<div id="app"></div><div id="modal-root"></div><div id="toast"></div>'});
      requests.push(pathname);
      return route.fulfill({contentType:'application/json', body:JSON.stringify({
        provider:'OpenStreetMap',
        results:[{label:'Example Hospital, Example Road', postcode:'CH1 1AA', latitude:53.4, longitude:-3, place_id:'first'}]
      })});
    });
    await page.goto('http://address.test/');
    await page.addScriptTag({content:read('builder-fields.js')});
    const app = read('app.js').replace(
      /start\(\)\.catch\(error => \{ app\.innerHTML = .*?\}\);/,
      ''
    );
    await page.addScriptTag({content:app});
    await page.evaluate(() => {
      document.querySelector('#app').innerHTML = `
        <div class="field address-search">
          <input id="ordinary" data-address-search="true" data-address-target="ordinary">
          <div id="ordinary-results" data-address-results="ordinary"></div>
        </div><form id="builder"></form>`;
      document.querySelector('#builder').innerHTML = AlignFields.render([
        {id:'location',type:'address',label:'Location',show_when:{}},
        {id:'legacy',type:'text',label:'Address',show_when:{}}
      ]);
    });
    await page.locator('#ordinary').fill('Example Hospital');
    await page.clock.runFor(1000);
    await page.locator('#ordinary-results [data-action="choose-address"]').waitFor();
    await page.locator('#ordinary-results [data-action="choose-address"]').click();
    await page.clock.runFor(3000);
    assert.equal(await page.locator('#ordinary').inputValue(), 'Example Hospital, Example Road');
    assert.deepEqual(requests, ['/api/address-search']);

    await page.locator('#ordinary').fill('Example Hospita');
    await page.clock.runFor(1000);
    await page.locator('#ordinary-results [data-action="choose-address"]').waitFor();
    await page.locator('#builder').click({position:{x:1,y:1}});
    await page.locator('#ordinary').fill('Example Hospital again');
    await page.clock.runFor(1000);
    await page.locator('#ordinary-results [data-action="choose-address"]').waitFor({state:'visible'});
    await page.locator('#ordinary-results [data-action="choose-address"]').click();
    assert.equal(await page.locator('#ordinary').inputValue(), 'Example Hospital, Example Road');
    assert.deepEqual(requests, ['/api/address-search', '/api/address-search', '/api/address-search']);

    await page.locator('#entry-location').fill('Example Hospital');
    await page.clock.runFor(1000);
    await page.locator('#entry-location-results [data-address-index]').waitFor();
    await page.locator('#entry-location-results [data-address-index]').click();
    await page.clock.runFor(3000);
    const selected = await page.evaluate(() => JSON.parse(document.querySelector('#entry-location').dataset.addressValue));
    assert.equal(selected.place_id, 'first');
    assert.equal(selected.latitude, 53.4);
    assert.deepEqual(requests, ['/api/address-search', '/api/address-search', '/api/address-search', '/api/builder/address-search']);

    await page.locator('#entry-legacy').fill('Example Hospital');
    await page.clock.runFor(1000);
    await page.locator('#entry-legacy-results [data-address-index]').waitFor();
    await page.locator('#entry-legacy').press('Enter');
    assert.equal(await page.locator('#entry-legacy').inputValue(), 'Example Hospital, Example Road');
    assert.equal(await page.locator('#entry-legacy-results').isHidden(), true);
    assert.deepEqual(requests, ['/api/address-search', '/api/address-search', '/api/address-search', '/api/builder/address-search']);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

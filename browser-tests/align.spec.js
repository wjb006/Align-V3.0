const { chromium, webkit, devices } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
fs.mkdirSync(path.join(ROOT, 'test-results'), {recursive:true});
const build152 = fs.readFileSync(path.join(ROOT, 'static', 'build152.js'), 'utf8');
const personalPlanner = fs.readFileSync(path.join(ROOT, 'static', 'personal-planner.js'), 'utf8');
const appSource = fs.readFileSync(path.join(ROOT, 'static', 'app.js'), 'utf8');

function sourceFunction(source, name) {
  const marker = `function ${name}(`;
  const start = source.indexOf(marker);
  if (start < 0) return '';
  const next = source.indexOf('\nfunction ', start + marker.length);
  return source.slice(start, next === -1 ? source.length : next).trim();
}

function sourceFunctions(source, names) {
  const missing = names.filter(name => source.indexOf(`function ${name}(`) < 0);
  assert.equal(missing.length, 0, `static/app.js is missing ${missing.join(', ')}`);
  return names.map(name => sourceFunction(source, name)).join('\n');
}

const monthPayload = {
  month: '2026-10', start: '2026-09-28', end: '2026-11-01',
  imported_events: [],
  events: [{id:10,title:'Dentist',location:'High Street',
    start_at:'2026-10-07T14:00:00',end_at:'2026-10-07T15:00:00',all_day:false}]
};

function createApiStore() {
  const favourites = new Map();
  const contacts = new Map([[1,{id:1,name:'Villa Medical Centre',address:'12 Medical Road, Warrington',phone:'01925 555123'}]]);
  return {
    favourites,
    contacts,
    handle(pathname, options) {
      if (pathname === '/api/contacts' && (!options.method || options.method === 'GET')) return {contacts:Array.from(contacts.values())};
      if (pathname === '/api/contacts' && options.method === 'POST') {
        const body = JSON.parse(options.body || '{}');
        const contact = {id:2,name:body.name,address:body.address || '',phone:body.phone || ''};
        contacts.set(contact.id, contact);
        return {contact,saved:true};
      }
      if (pathname.startsWith('/api/contacts/') && options.method === 'PUT') {
        const id = Number(pathname.split('/').pop());
        const current = contacts.get(id);
        if (!current) throw new Error('Contact not found');
        const body = JSON.parse(options.body || '{}');
        const contact = {...current,...body,id};
        contacts.set(id,contact);
        return {contact,saved:true};
      }
      if (pathname === '/api/favourites' && (!options.method || options.method === 'GET')) {
        return {favourites: Array.from(favourites.values())};
      }
      if (pathname === '/api/favourites' && options.method === 'POST') {
        const body = JSON.parse(options.body || '{}');
        const key = body.entity_type + ':' + body.entity_key;
        if (body.active) {
          const favourite = {
            entity_type: body.entity_type, entity_key: body.entity_key,
            label: body.label, value: body.value || '', metadata: body.metadata || {}
          };
          favourites.set(key, favourite);
          return {favourite};
        }
        favourites.delete(key);
        return {favourite:null};
      }
      if (pathname.startsWith('/api/month?month=')) return monthPayload;
      if (pathname.startsWith('/api/week?start=')) return {start:'2026-10-05',days:[],shifts:[],annual_leave:[],events:[]};
      throw new Error('Unexpected API request: ' + pathname);
    }
  };
}

async function bootstrap(page, store) {
  await page.setContent('<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body><div class="app-shell"><main id="app"></main><nav class="tab-bar" id="bottom-navigation"></nav></div><div id="modal-root"></div><div id="toast"></div></body></html>');
  const mobileDevice = process.env.MOBILE_DEVICE || '';
  if (mobileDevice) {
    const viewport = devices[mobileDevice].viewport;
    await page.setViewportSize({width:viewport.width,height:viewport.height});
  }
  await page.route('**/api/**', async route => {
    try {
      const request = route.request();
      const body = request.postData() || '';
      const result = store.handle(new URL(request.url()).pathname + new URL(request.url()).search,
        {method: request.method(), body});
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(result)});
    } catch (error) {
      await route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({message:error.message})});
    }
  });
  await page.addScriptTag({content: [
    'window.state={scheduleView:"week",scheduleMonth:"2026-10",scheduleWeek:"2026-10-05",scheduleFocus:"2026-10-05",',
    'scheduleData:{start:"2026-10-05",days:[],shifts:[],annual_leave:[],events:[]},monthData:null,',
    'sectionData:{events:[{source_kind:"align",title:"Existing meeting"}]},boot:{sections:[]},tab:"calendar"};',
    'window.api=async function(path,options){var r=await fetch(new URL(path,"http://align.test").toString(),{method:(options&&options.method)||"GET",',
    'headers:{"Content-Type":"application/json"},body:options&&options.body?JSON.stringify(options.body):undefined});',
    'var p=await r.json();if(!r.ok)throw new Error(p.message||"Request failed");return p;};',
    'window.toast=function(message){document.querySelector("#toast").textContent=message};',
    'window.render=function(){if(state.tab==="organiser")return;if(typeof renderBottomNavigation==="function")renderBottomNavigation();document.querySelector("#app").innerHTML=window.renderCalendar()};',
    'window.isoToday=function(){return "2026-10-05"};',
    'window.fromIso=function(v){return new Date(v+"T12:00:00")};',
    'window.toIso=function(v){return v.getFullYear()+"-"+String(v.getMonth()+1).padStart(2,"0")+"-"+String(v.getDate()).padStart(2,"0")};',
    'window.monday=function(value=new Date()){var day=value.getDay()||7;value=new Date(value);value.setDate(value.getDate()-day+1);return value};',
    'window.prettyDate=function(v){var p=String(v).slice(0,10).split("-");return p[2]+"/"+p[1]+"/"+p[0]};',
    'window.escapeHtml=function(v){return String(v==null?"":v).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"}[c]})};',
    'window.hours=function(v){return Number(v).toFixed(1).replace(".0","")+"h"};',
    'window.WEEK_DAYS=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"];',
    'window.addDays=function(day,offset){var d=fromIso(day);d.setDate(d.getDate()+offset);return toIso(d)};',
    'window.appleDestinationLink=function(a,b,label){return escapeHtml(label||a)};',
    'window.postTravelSummary=window.savedTravelSummary=function(){return ""};window.travelReminderMinutes=function(){return 0};window.eventViewAttributes=function(){return ""};window.travelCard=function(){return ""};'
  ].join('')});
  await page.addScriptTag({content: sourceFunctions(appSource, ['sectionEventDate', 'eventSectionColour', 'eventChoice', 'dayHeading', 'renderEventRow', 'renderGroupedEventRows'])});
  await page.addScriptTag({content: build152});
  await page.evaluate(() => window.dispatchEvent(new Event('load')));
  await page.evaluate(() => { state.boot={master:{locations:[],shift_types:[]},sections:[]}; state.tab='calendar'; });
  await page.addStyleTag({content: fs.readFileSync(path.join(ROOT, 'static', 'styles.css'), 'utf8')});
  await page.waitForFunction(() => window.ALIGN152 && window.ALIGN152.loaded === true);
  await page.evaluate(() => window.ALIGN152.contactsReady);
  await page.waitForFunction(() => Array.isArray(window.ALIGN152.contacts) && window.ALIGN152.contacts.length === 1);
}

async function verifyOwnerBuilderMenuScroll(context) {
  const page = await context.newPage();
  await page.setViewportSize({width: 390, height: 320});
  const html = fs.readFileSync(path.join(ROOT, 'static', 'owner-builder.html'), 'utf8')
    .replace(/<link\b[\s\S]*?>/gi, '')
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '');
  const menus = Array.from({length: 30}, (_, index) => ({
    id: `menu_${index}`, parent_id: '', title: `Menu item ${index + 1}`,
    description: '', icon: '○', colour: '#365CE6', destination: 'note',
    layout_id: '', content: '', active: true
  }));
  const document = {
    startup: {title: 'Welcome', description: '', button: 'Continue', fields: []},
    menus, layouts: [], navigation: [], home_sections: [], travel_results: {},
    formatting: {}
  };
  await page.route('http://builder.test/**', route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/builder/config') {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({revision: 1, published_revision: 1, draft: document, published: document})
      });
    }
    if (pathname === '/owner-builder.html') {
      return route.fulfill({contentType: 'text/html', body: html});
    }
    return route.fulfill({status: 404, body: 'Not found'});
  });
  await page.goto('http://builder.test/owner-builder.html', {waitUntil: 'domcontentloaded'});
  await page.addStyleTag({content: fs.readFileSync(path.join(ROOT, 'static', 'styles.css'), 'utf8')});
  await page.addStyleTag({content: fs.readFileSync(path.join(ROOT, 'static', 'owner-builder.css'), 'utf8')});
  for (const file of ['builder-fields.js', 'builder-finance.js', 'owner-builder.js', 'owner-builder-layout.js']) {
    await page.addScriptTag({content: fs.readFileSync(path.join(ROOT, 'static', file), 'utf8')});
  }
  await page.locator('#edit-search').fill('Menu item');
  await page.waitForSelector('.builder-jump');
  await page.locator('#builder-nav-toggle').click();
  assert.equal(await page.locator('#builder-nav-toggle').getAttribute('aria-expanded'), 'true');
  const sidebar = page.locator('#builder-sidebar');
  const sidebarMetrics = await sidebar.evaluate(element => ({
    scrollHeight: element.scrollHeight,
    clientHeight: element.clientHeight,
    overflowY: getComputedStyle(element).overflowY,
    position: getComputedStyle(element).position,
    viewport: {width: window.innerWidth, height: window.innerHeight}
  }));
  assert(sidebarMetrics.scrollHeight > sidebarMetrics.clientHeight,
    `Builder sidebar should scroll when its contents exceed the viewport: ${JSON.stringify(sidebarMetrics)}`);
  await sidebar.evaluate(element => { element.scrollTop = element.scrollHeight; });
  assert((await sidebar.evaluate(element => element.scrollTop)) > 0);
  await page.locator('#builder-sidebar [data-tab="menus"]').click();
  await page.waitForSelector('.builder-panel h2');
  assert.equal(await page.locator('.builder-panel h2').first().textContent(), 'Menu structure');
  assert.equal(await page.locator('#builder-nav-toggle').getAttribute('aria-expanded'), 'false');
  const item = page.locator('[data-item="menu_29"]');
  await item.scrollIntoViewIfNeeded();
  const scrollBefore = await page.evaluate(() => window.scrollY);
  await item.click();
  const scrollAfter = await page.evaluate(() => window.scrollY);
  assert.equal(scrollAfter, scrollBefore, 'Selecting a menu item should not jump the editor back to the top');
  await page.close();
}

async function verifyManagementStudio(browser) {
  const context = await browser.newContext({viewport:{width:1440,height:1000}});
  const page = await context.newPage();
  const pageErrors = [];
  const failedRequests = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  page.on('requestfailed', request => failedRequests.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText || 'request failed'}`));
  const document = {
    startup:{title:'Welcome',description:'',button:'Continue',fields:[]},
    menus:[],layouts:[],
    navigation:[
      {id:'today',title:'Today',icon:'⌂',destination:'today',active:true},
      {id:'inbox',title:'Inbox',icon:'☑',destination:'inbox',active:true},
      {id:'planner',title:'Planner',icon:'▦',destination:'planner',active:true},
      {id:'more',title:'More',icon:'•••',destination:'more',active:true}
    ],
    home_sections:[
      {id:'today',title:'Today at a glance',visible:true,sort_order:10},
      {id:'upcoming',title:'Upcoming Events',visible:true,sort_order:30}
    ],
    travel_results:{},
    formatting:{},
    appearance:{
      colors:{accent:'#365ce6',canvas:'#f7f8fc',surface:'#ffffff',text:'#162147'},
      banners:{today:'#172a62',upcoming:'#365ce6',annual_leave:'#0f9d8a',section_detail:'#365ce6'},
      events:{style:'standard',density:'comfortable',accent:'#6577bd'},
      type:{scale:'default',corners:'soft',font:'system',heading:'bold',theme:'light'},
      calendar:{month_cell:'#f1f5fd',month_weekend:'#e9eefb',month_date_band:'#dfe7fb',list_day:'#f1f5fd',list_day_header:'#edf2ff',today_cell:'#e4ecff',week_headings:'show'}
    },
    appearance_permissions:{colors:false,banners:false,events:false,type:false,calendar:false}
  };
  const saved = {revision:4,published_revision:4,draft:document,published:document};
  const writes = [];
  const html = fs.readFileSync(path.join(ROOT,'static','management-studio.html'),'utf8')
    .replace(/<link\b[^>]*>/gi,'')
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
  await page.route('http://management.test/**', async route => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (pathname === '/management-studio.html') {
      return route.fulfill({contentType:'text/html',body:html});
    }
    if (pathname === '/api/builder/config' && request.method() === 'GET') {
      return route.fulfill({contentType:'application/json',body:JSON.stringify(saved)});
    }
    if (pathname === '/api/builder/config' || pathname === '/api/builder/publish') {
      const payload = JSON.parse(request.postData() || '{}');
      assert.equal(payload.revision,saved.revision);
      writes.push({pathname,document:payload.document});
      saved.revision += 1;
      if (pathname.endsWith('/publish')) saved.published_revision = saved.revision;
      saved.draft = payload.document;
      if (pathname.endsWith('/publish')) saved.published = payload.document;
      return route.fulfill({contentType:'application/json',body:JSON.stringify(saved)});
    }
    return route.fulfill({status:404,body:'Not found'});
  });
  try {
    await page.goto('http://management.test/management-studio.html',{waitUntil:'domcontentloaded'});
    assert.match(await page.locator('#management-phone').innerText(),/Team check-in/,
      'The initial phone preview must be usable before Studio APIs load');
    await page.addStyleTag({content:fs.readFileSync(path.join(ROOT,'static','styles.css'),'utf8')});
    await page.addStyleTag({content:fs.readFileSync(path.join(ROOT,'static','management-studio.css'),'utf8')});
    await page.addScriptTag({content:fs.readFileSync(path.join(ROOT,'static','builder-fields.js'),'utf8')});
    await page.addScriptTag({content:fs.readFileSync(path.join(ROOT,'static','owner-builder.js'),'utf8')});
    await page.addScriptTag({content:fs.readFileSync(path.join(ROOT,'static','management-studio.js'),'utf8')});
    await page.addScriptTag({content:fs.readFileSync(path.join(ROOT,'static','management-studio-nav.js'),'utf8')});
    // Readiness is the rendered editor, not a shared status label. The nav script
    // intentionally writes the Builder status when it activates Home, so a fast
    // WebKit response can legitimately be followed by that label and cause a race.
    await page.locator('[data-unified-tab="colors"]').click();
    try {
      await page.waitForFunction(() => {
        const input = document.querySelector('[data-setting="appearance.colors.accent"]');
        // WebKit may expose an unsupported colour input as type="text" while
        // retaining the requested HTML type attribute and editor control.
        return Boolean(input && input.isConnected && input.getAttribute('type') === 'color');
      }, null, {timeout:30000});
    } catch (error) {
      const status = await page.locator('#management-status').textContent().catch(() => 'missing');
      const editor = await page.locator('#management-editor').innerText().catch(() => 'missing');
      const colorInputs = await page.locator('[data-setting="appearance.colors.accent"]').evaluateAll(nodes =>
        nodes.map(node => ({type:node.type, connected:node.isConnected, html:node.outerHTML}))
      ).catch(() => []);
      throw new Error(`${error.message}; Management Studio status: ${status}; editor: ${editor.slice(0,500)}; color inputs: ${JSON.stringify(colorInputs)}; page errors: ${pageErrors.join(' | ') || 'none'}; failed requests: ${failedRequests.join(' | ') || 'none'}`);
    }
    // Switch the real unified navigation to the startup editor before editing it.
    // Dispatching the builder event alone renders the editor behind the currently active Colours pane.
    await page.locator('[data-unified-tab="startup"]').click();
    await page.locator('[data-startup-editor] input[data-prop="title"]').waitFor({state:'visible'});
    await page.locator('[data-startup-editor] input[data-prop="title"]').fill('Welcome V2');
    await page.locator('#save').click();
    await page.waitForFunction(() => document.querySelector('#builder-status')?.textContent.startsWith('Draft saved'));
    assert.equal(writes.at(-1).document.startup.title,'Welcome V2');
    // Return to Home before checking the Home tab state and continuing preview tests.
    await page.locator('[data-unified-tab="dashboard"]').click();
    assert.equal(await page.locator('[data-unified-tab="dashboard"].is-active').count(),1);
    assert.equal(await page.locator('.management-device-screen').count(),1);
    assert.match(await page.locator('#management-phone').innerText(),/Sample event/);
    assert.equal(await page.locator('#management-phone').evaluate(el =>
      getComputedStyle(el.querySelector('.management-phone')).getPropertyValue('--preview-accent').trim()
    ),'#365ce6');
    assert.equal(await page.locator('[data-unified-tab="dashboard"].is-active').count(),1);
    await page.locator('[data-management-tab="pages"]').click();
    assert.equal(await page.locator('#design-pane').isHidden(),false);
    assert.equal(await page.locator('#builder-pane').isHidden(),true);
    assert.equal(await page.locator('[data-management-tab="pages"].is-active').count(),1);
    assert.equal(await page.locator('[data-unified-tab="dashboard"].is-active').count(),0);
    assert.equal(await page.locator('[data-home-title]').count() > 0, true);
    const sectionsHome = page.locator('#management-phone [data-preview-home-section="menus"]');
    if (await sectionsHome.count()) await sectionsHome.click();
    const createMatrix = page.locator('#management-phone [data-preview-create-layout]');
    if (await createMatrix.count()) {
      await createMatrix.click();
      assert.equal(await page.locator('#builder-content [data-layout-editor]').count(),1,
        'Creating from the phone Sections area should open the section and matrix editor');
      assert.equal(await page.locator('#builder-content [data-field-editor]').count(),1,
        'A new database matrix should open with its first question ready to edit');
      assert.equal(await page.locator('#builder-content [data-prop="review_before_save"]').isChecked(),true,
        'New section input should include a review step by default');
      assert.match(await page.locator('#builder-content').innerText(),/Step 1 of 3[\s\S]*Step 2 of 3[\s\S]*Step 3 of 3/);
      await page.locator('#save').click();
      await page.waitForFunction(() => document.querySelector('#builder-status')?.textContent.startsWith('Draft saved'));
      await page.locator('[data-management-tab="pages"]').click();
    }
    await page.locator('#management-phone [data-preview-home-section="today"] .mp-drag-handle').click();
    await page.waitForFunction(() => document.activeElement?.matches('[data-home-title]'));
    assert.equal(await page.evaluate(() => document.activeElement?.matches('[data-home-title]')),true,
      'Selecting a home area in the phone preview should focus its editor');
    await page.locator('#management-phone [data-preview-home-section="upcoming"]').dragTo(
      page.locator('#management-phone [data-preview-home-section="today"]')
    );
    assert.deepEqual((await page.locator('#management-phone [data-preview-home-section]').evaluateAll(items =>
      items.map(item => item.dataset.previewHomeSection)
    )).slice(0,2),['upcoming','today'],'Dragging a preview block should reorder the draft preview');
    await page.locator('#save').click();
    await page.waitForFunction(() => document.querySelector('#management-status')?.textContent.startsWith('Draft saved'));
    assert.deepEqual(writes.at(-1).document.home_sections.slice().sort((a,b)=>a.sort_order-b.sort_order).map(item=>item.id).slice(0,2),['upcoming','today']);
    await page.locator('#management-phone [data-preview-nav-id="planner"]').click();
    assert.equal(await page.locator('#builder-pane').isHidden(),false,
      'Selecting a bottom button in the phone should open its navigation editor');
    assert.equal(await page.evaluate(() => document.activeElement?.matches('[data-prop^="nav-title-"]')),true);
    await page.locator('[data-management-tab="pages"]').click();
    await page.locator('#management-phone [data-preview-nav-id="planner"]').dragTo(
      page.locator('#management-phone [data-preview-nav-id="today"]')
    );
    assert.deepEqual((await page.locator('#management-phone [data-preview-nav-id]').evaluateAll(items =>
      items.map(item => item.dataset.previewNavId)
    )).slice(0,2),['planner','today'],'Dragging a phone button should reorder navigation');
    await page.locator('#save').click();
    await page.waitForFunction(() => document.querySelector('#management-status')?.textContent.startsWith('Draft saved'));
    assert.deepEqual(writes.at(-1).document.navigation.slice(0,2).map(item=>item.id),['planner','today']);
    await page.locator('[data-management-tab="colors"]').click();
    assert.equal(await page.locator('[data-unified-tab="colors"].is-active').count(),1);
    assert.equal(await page.locator('[data-management-tab="pages"].is-active').count(),0);

    await page.locator('[data-management-tab="colors"]').click();
    assert.equal(await page.locator('#builder-pane').isHidden(),true);
    assert.equal(await page.locator('#design-pane').isHidden(),false);
    await page.locator('[data-setting="appearance.colors.accent"]').evaluate(element => {
      element.value='#123456';
      element.dispatchEvent(new Event('input',{bubbles:true}));
    });
    assert.equal(await page.locator('#management-phone .management-phone').evaluate(el =>
      getComputedStyle(el).getPropertyValue('--preview-accent').trim()
    ),'#123456');
    assert.equal(await page.locator('#save').isEnabled(),true);
    await page.locator('#save').click();
    await page.waitForFunction(() => document.querySelector('#management-status')?.textContent.startsWith('Draft saved'));
    assert.equal(writes.at(-1).document.appearance.colors.accent,'#123456');
    assert.equal(await page.locator('#publish').isEnabled(),true,
      'A saved but unpublished Builder draft should be publishable without further edits');

    await page.locator('[data-management-tab="users"]').click();
    await page.locator('[data-setting="appearance_permissions.colors"]').check();
    await page.locator('[data-management-tab="events"]').click();
    await page.locator('[data-setting="appearance.events.density"]').selectOption('compact');
    assert.equal(await page.locator('#management-phone .management-phone-event').first().evaluate(el =>
      getComputedStyle(el).paddingTop
    ),'8px');
    await page.locator('[data-preview-screen="planner"]').click();
    assert.match(await page.locator('#management-phone').innerText(),/PLANNER/);
    await page.locator('[data-preview-screen="calendar"]').click();
    await page.locator('[data-management-tab="type"]').click();
    await page.locator('[data-setting="appearance.type.theme"]').selectOption('dark');
    assert.equal(await page.locator('#management-phone .management-phone').getAttribute('data-theme'),'dark');
    await page.locator('[data-setting="appearance.type.theme"]').selectOption('light');
    assert.equal(await page.locator('#export').isEnabled(),true);
    await page.locator('#import').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from('{"nope":1}')});
    await page.waitForFunction(() => /not an Align design/.test(document.querySelector('#management-status').textContent));
    await page.locator('#import').setInputFiles({name:'ok.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({align_design:1,appearance:{colors:{accent:'#0a0b0c'}}}))});
    await page.waitForFunction(() => /Design imported/.test(document.querySelector('#management-status').textContent));
    await page.locator('[data-management-tab="history"]').click();
    assert.equal(await page.locator('[data-unified-tab="history"].is-active').count(),1);
    assert.equal(await page.locator('[data-unified-tab="colors"].is-active').count(),0);
    await page.waitForFunction(() => document.querySelector('#management-history')?.textContent.length > 0);
    assert.match(await page.locator('#management-phone').innerText(),/WEEK COMMENCING/);
    await page.locator('[data-management-tab="colors"]').click();
    page.once('dialog', dialog => dialog.accept());
    await page.locator('[data-preset="forest"]').click();
    assert.equal(await page.locator('[data-setting="appearance.colors.accent"]').inputValue(),'#2f7d5b');
    await page.locator('[data-revert-section="colors"]').click();
    assert.notEqual(await page.locator('[data-setting="appearance.colors.accent"]').inputValue(),'#2f7d5b');
    page.once('dialog', dialog => dialog.accept());
    await page.locator('[data-preset="forest"]').click();
    await page.locator('[data-setting="appearance.colors.text"]').evaluate(element => {
      element.value='#f0f0f0'; element.dispatchEvent(new Event('input',{bubbles:true}));
    });
    assert.match(await page.locator('.management-contrast').innerText(),/below the recommended/);
    let publishPrompt = '';
  page.once('dialog', dialog => { publishPrompt = dialog.message(); dialog.accept(); });
    await page.locator('#publish').click();
    await page.waitForFunction(() => (document.querySelector('#management-status')?.textContent || '').startsWith('Published to everyone on the website'));
    assert.equal(writes.at(-1).pathname,'/api/builder/publish');
  assert.match(publishPrompt,/Readability warning/);
    assert.equal(writes.at(-1).document.appearance_permissions.colors,true);
    assert.equal(writes.at(-1).document.appearance.events.density,'compact');
    assert.equal(await page.locator('a[href="/owner-builder"]').count(),0,
      'The unified Management Studio should not send normal users to the legacy Owner Builder page');
    assert.equal(await page.locator('iframe').count(),0,'The Builder must be embedded without an iframe');
    assert.deepEqual(pageErrors,[],'Builder and Design should initialize without JavaScript exceptions');
    await page.screenshot({path:path.join(ROOT,'test-results','management-studio-desktop.png'),fullPage:true});

    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(() =>
      document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1
    ),true);
    assert(await page.locator('.unified-sidebar').evaluate(el => getComputedStyle(el).overflowX === 'auto'));
    const mobilePublish = await page.locator('#publish').boundingBox();
    assert(mobilePublish && mobilePublish.x >= 0 &&
      mobilePublish.x + mobilePublish.width <= await page.evaluate(() => document.documentElement.clientWidth) + 1);
    await page.screenshot({path:path.join(ROOT,'test-results','management-studio-mobile.png'),fullPage:true});
  } finally {
    await context.close();
  }
}

async function main() {
  const browserName = process.env.BROWSER || 'chromium';
  const mobileDevice = process.env.MOBILE_DEVICE || '';
  const browserType = browserName === 'webkit' ? webkit : chromium;
  const browser = await browserType.launch({headless:true});
  const context = await browser.newContext(mobileDevice ? devices[mobileDevice] : {});
  try {
    const page = await context.newPage();
    const store = createApiStore();

    await bootstrap(page, store);
    const parsedEntry = await page.evaluate(() => window.ALIGN152.smartDateTime(
      'Doctors at St Catherines 09/10/26 at 11',
      new Date(2026,9,2,9)
    ));
    assert.deepEqual(parsedEntry, {
      date:'2026-10-09',start:'11:00',end:'12:00',title:'Doctors',location:'St Catherines'
    });

    await page.evaluate(() => {
      state.tab='organiser';
      document.querySelector('#app').innerHTML =
        '<form data-form="organiser-event"><input name="title"><input name="date"><input name="start_time"><input name="end_time"><input type="checkbox" name="all_day"><input name="location"><textarea name="notes"></textarea></form>';
    });
    await page.waitForSelector('[data-build152-fav-title]');
    await page.waitForFunction(() => document.querySelectorAll('[data-build152-contact] option').length === 2);
    await page.locator('input[name="title"]').fill('Appointment at Villa Medical Centre');
    await page.locator('input[name="title"]').dispatchEvent('input');
    assert.equal(await page.locator('[data-build152-contact]').inputValue(), '1');
    assert.equal(await page.locator('input[name="location"]').inputValue(), '12 Medical Road, Warrington');
    assert.equal(await page.locator('input[name="build152_contact_phone"]').count(),0);
    assert.equal(await page.locator('[data-build153-contact-preview] a[href^="tel:"]').getAttribute('href'),'tel:01925%20555123');
    await page.locator('input[name="title"]').fill('Doctors at St Catherines 09/10/26 at 11');
    await page.locator('input[name="title"]').dispatchEvent('input');
    assert.equal(await page.locator('input[name="date"]').inputValue(),'2026-10-09');
    assert.equal(await page.locator('input[name="start_time"]').inputValue(),'11:00');
    assert.equal(await page.locator('input[name="end_time"]').inputValue(),'12:00');
    assert.equal(await page.locator('input[name="location"]').inputValue(),'St Catherines');
    assert.equal(await page.locator('input[name="title"]').inputValue(),'Doctors at St Catherines 09/10/26 at 11');
    await page.locator('input[name="title"]').blur();
    assert.equal(await page.locator('input[name="title"]').inputValue(),'Doctors');

    await page.locator('input[name="title"]').fill('Appointment at Villa Medical Centre');
    await page.locator('input[name="title"]').dispatchEvent('input');
    await page.locator('[data-build153-manage-contacts]').click();
    await page.locator('.build153-contact-manager-backdrop [data-build153-contact-action="edit"]').click();
    await page.locator('.build153-contact-manager-backdrop input[name="address"]').fill('14 New Medical Road');
    await page.locator('.build153-contact-manager-backdrop input[name="phone"]').fill('01925 555987');
    await page.locator('.build153-contact-manager-backdrop button.primary-button').click();
    await page.waitForFunction(() => window.ALIGN152.contacts.find(x => x.id === 1)?.phone === '01925 555987');
    assert.equal(await page.locator('input[name="location"]').inputValue(),'14 New Medical Road');
    assert.equal(await page.locator('[data-build153-contact-preview] a[href^="tel:"]').getAttribute('href'),'tel:01925%20555987');
    await page.locator('.build153-contact-manager-backdrop [data-build153-contact-action="close"]').first().click();
    await page.locator('[data-build152-fav-title]').click();
    await page.waitForTimeout(5);
    await page.locator('[data-build152-contact]').dispatchEvent('change');
    await page.locator('form[data-form="organiser-event"]').evaluate(form => form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
    assert.match(await page.locator('textarea[name="notes"], input[name="notes"]').inputValue(), /Align contact/);
    assert.doesNotMatch(await page.locator('textarea[name="notes"], input[name="notes"]').inputValue(), /01925 555987/);
    assert.match(await page.evaluate(() => window.ALIGN152.eventContactMarkup('[Align contact] {"id":1}')), /01925 555987/);

    const suggestions = await page.locator('#align152-title-suggestions option').evaluateAll(
      options => options.map(option => option.value)
    );
    assert(suggestions.includes('Existing meeting'));

    await page.locator('input[name="title"]').fill('');
    await page.locator('input[name="title"]').pressSequentially('Dentist', {delay: 8});
    await page.locator('input[name="location"]').fill('');
    await page.locator('input[name="location"]').pressSequentially('High Street', {delay: 8});
    assert.equal(await page.locator('input[name="title"]').inputValue(), 'Dentist');
    assert.equal(await page.locator('input[name="location"]').inputValue(), 'High Street');
    await page.locator('[data-build152-fav-title]').click();
    await page.locator('[data-build152-fav-location]').click();
    await page.waitForTimeout(25);
    assert.equal(await page.locator('[data-build152-fav-title]').textContent(), '★ Saved title');
    assert.equal(await page.locator('[data-build152-fav-location]').textContent(), '★ Saved location');
    assert.equal(store.favourites.size, 3);

    const page2 = await context.newPage();
    await bootstrap(page2, store);
    await page2.evaluate(() => {
      state.tab='organiser';
      document.querySelector('#app').innerHTML =
        '<form data-form="organiser-event"><input name="title"><input name="location"></form>';
    });
    await page2.waitForSelector('[data-build152-fav-title]');
    const persisted = await page2.evaluate(() => ({
      titleSuggestion: Array.from(document.querySelectorAll('#align152-title-suggestions option'))
        .some(x => x.value === 'Dentist'),
      locationSuggestion: Array.from(document.querySelectorAll('#align152-location-suggestions option'))
        .some(x => x.value === 'High Street')
    }));
    assert.equal(persisted.titleSuggestion, true);
    assert.equal(persisted.locationSuggestion, true);
    await page2.close();

    await page.evaluate(() => {
      state.tab='calendar';
      state.monthData = {
        month:'2026-10',start:'2026-09-28',end:'2026-11-01',
        imported_events:[],
        events:[{title:'Dentist',location:'High Street',start_at:'2026-10-07T14:00:00',
          end_at:'2026-10-07T15:00:00',all_day:false}]
      };
      state.scheduleMonth='2026-10';
      state.scheduleView='list';
      render();
    });
    await page.waitForSelector('.build152-list-day');
    const listText = await page.locator('#app').innerText();
    assert.match(listText,/Dentist/);
    assert.doesNotMatch(listText,/shift|annual leave/i);
    await page.screenshot({path: 'test-results/calendar-list-mobile.png', fullPage: true});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), true);

    assert.equal(await page.locator('[data-build152-view]').count(),0);

    // Today at a Glance: weather banner, three following days, schedule separation,
    // and removal of events whose end time has passed.
    const todayPage = await context.newPage();
    await todayPage.setContent('<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body><div class="app-shell"><main id="app"></main></div></body></html>');
    if (mobileDevice) {
      const todayViewport = devices[mobileDevice].viewport;
      await todayPage.setViewportSize({width:todayViewport.width,height:todayViewport.height});
    }
    await todayPage.addStyleTag({content: fs.readFileSync(path.join(ROOT, 'static', 'styles.css'), 'utf8')});
    await todayPage.addScriptTag({content: [
      'window.state={tab:"today",boot:{beta:{email:"test@example.com"},builder:{document:{base_structure:{weather:{enabled:true,refresh_minutes:15}}}},',
      'settings:{user_name:"Test"},personal:{today:"2026-10-05",preferences:{show_todos:false},events:[],items:[]}}};',
      'window.escapeHtml=function(v){return String(v==null?"":v).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"}[c]})};',
      'window.prettyDate=function(v){var p=String(v).slice(0,10).split("-");return p[2]+"/"+p[1]+"/"+p[0]};',
      'window.render=function(){document.querySelector("#app").innerHTML=personalToday()};',
      'window.api=async function(){return {}};',
      'window.renderUpcomingEvent=function(event){return "<article class=\\"card upcoming-event\\"><strong>"+escapeHtml(event.title)+"</strong></article>"};'
    ].join('')});
    await todayPage.addScriptTag({content: fs.readFileSync(path.join(ROOT, 'static', 'dates.js'), 'utf8')});
    await todayPage.addScriptTag({content: sourceFunctions(appSource, ['homeSectionTitle', 'homeSectionContent', 'eventChoice', 'eventLocationKey', 'renderGroupedEventRows'])});
    await todayPage.addScriptTag({content: personalPlanner});
    await todayPage.evaluate(() => {
      personalWeather = {
        source:'Open-Meteo',
        checked_at:'2026-10-05T08:00:00Z',
        place:'Birkenhead',
        current:{weather_code:1,temperature_2m:14},
        daily:{
          time:['2026-10-05','2026-10-06','2026-10-07','2026-10-08'],
          weather_code:[1,2,3,61],
          temperature_2m_min:[9,10,11,12],
          temperature_2m_max:[16,17,18,19],
          precipitation_probability_max:[20,30,40,60]
        }
      };
      Date.now = () => new Date('2026-10-05T12:00:00').getTime();
      weatherContext=JSON.stringify(['test@example.com','']);
      weatherCheckedAt=Date.now();
      state.boot.personal.events=[
        {title:'Passed appointment',start_at:'2026-10-05T08:00',end_at:'2026-10-05T09:00',all_day:false},
        {title:'Future appointment',start_at:'2026-10-05T15:00',end_at:'2026-10-05T16:00',all_day:false}
      ];
      document.querySelector('#app').innerHTML=personalToday();
    });
    await todayPage.waitForSelector('.today-weather-banner');
    assert.equal(await todayPage.locator('.today-weather-next .today-weather-day').count(),3);
    assert.equal(await todayPage.locator('.today-weather-location strong').textContent(),'Birkenhead');
    assert(await todayPage.locator('.today-weather-updated').textContent().then(t=>t.includes('Updated')));
    assert.equal(await todayPage.locator('.today-weather-refresh').count(),1);
    assert.equal(await todayPage.locator('.today-weather-refresh').getAttribute('aria-label'),'Refresh weather');
    assert.equal(await todayPage.locator('button[data-personal="weather-view"]').count(),4);
    assert.equal(await todayPage.locator('button[data-personal="weather-view"][data-view="three"]').getAttribute('aria-pressed'),'true');
    await todayPage.locator('button[data-personal="weather-view"][data-view="daily"]').click();
    assert.equal(await todayPage.locator('.today-weather-days .today-weather-day').count(),4);
    await todayPage.locator('.today-weather-days [data-personal="weather-day"]').nth(2).click();
    assert.equal(await todayPage.locator('.today-weather-days .today-weather-day').count(),1);
    assert.equal(await todayPage.locator('button[data-personal="weather-view"][data-view="day"]').getAttribute('aria-pressed'),'true');
    await todayPage.locator('button[data-personal="weather-view"][data-view="hourly"]').click();
    assert.match(await todayPage.locator('.today-weather').innerText(),/Hourly forecast is not available/);
    await todayPage.locator('button[data-personal="weather-view"][data-view="three"]').click();
    assert.equal(await todayPage.locator('.today-weather-next .today-weather-day').count(),3);
    assert.equal(await todayPage.locator('select[data-personal="weather-view"]').count(),0);
    assert.equal(await todayPage.locator('h3#today-schedule-heading').textContent(),"Today’s Schedule");
    const todayText=await todayPage.locator('.today-event-list').innerText();
    assert.equal(todayText.includes('Passed appointment'),false);
    assert.equal(todayText.includes('Future appointment'),true);
    await todayPage.screenshot({path: 'test-results/today-at-a-glance.png', fullPage: true});
    const viewportWidth = await todayPage.evaluate(() => document.documentElement.clientWidth);
    assert.equal(await todayPage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), true);
    const weatherBox = await todayPage.locator('.today-weather-banner').boundingBox();
    const scheduleBox = await todayPage.locator('.today-schedule').boundingBox();
    const forecastBoxes = await todayPage.locator('.today-weather-day').evaluateAll(nodes => nodes.map(n => {
      const r=n.getBoundingClientRect();
      return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width};
    }));
    assert(weatherBox && weatherBox.x >= 0 && weatherBox.x + weatherBox.width <= viewportWidth + 1);
    assert(scheduleBox && scheduleBox.x >= 0 && scheduleBox.x + scheduleBox.width <= viewportWidth + 1);
    assert(forecastBoxes.every(r => r.left >= 0 && r.right <= viewportWidth + 1));
    assert(new Set(forecastBoxes.map(r => Math.round(r.top))).size === 1);
    assert(forecastBoxes[2].right <= viewportWidth + 1);
    await todayPage.close();

    await verifyOwnerBuilderMenuScroll(context);
    await verifyManagementStudio(browser);

    console.log(`PASS — Align V3.0 browser regressions: ${browserName}${mobileDevice ? ` (${mobileDevice})` : ''}; user flows, section records, calendar views, Studio draft/publish and phone preview`);
  } finally {
    await context.close();
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode=1; });

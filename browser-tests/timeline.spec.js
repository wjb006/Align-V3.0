const { chromium, webkit, devices } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const appSource = fs.readFileSync(path.join(ROOT, 'static', 'app.js'), 'utf8');
const styles = fs.readFileSync(path.join(ROOT, 'static', 'styles.css'), 'utf8');

function sourceFunction(name) {
  const marker = [`function ${name}(`, `async function ${name}(`]
    .map(value => ({value, index:appSource.indexOf(value)}))
    .filter(match => match.index >= 0)
    .sort((a,b) => a.index-b.index)[0];
  assert.ok(marker, `static/app.js is missing ${name}`);
  const next = appSource.slice(marker.index + marker.value.length)
    .search(/\n(?:async )?function /);
  return appSource.slice(marker.index, next < 0 ? undefined : marker.index + marker.value.length + next).trim();
}

async function main() {
  const browserType = process.env.BROWSER === 'webkit' ? webkit : chromium;
  const browser = await browserType.launch({headless:true});
  const deviceName = process.env.MOBILE_DEVICE || '';
  const context = await browser.newContext(deviceName ? devices[deviceName] : {viewport:{width:390,height:844},deviceScaleFactor:1});
  const page = await context.newPage();
  try {
    await page.setContent('<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body><div class="app-shell"><main id="app"></main></div><div id="modal-root"></div></body></html>');
    await page.addStyleTag({content:styles});
    await page.addScriptTag({content:`
      window.state={boot:{personal:{journey_provider:'configured'},settings:{user_address:'Home Road One'}},tab:'today',
        dailyInboundJourneys:{},dailyInboundLoading:{},dailyInboundErrors:{},postTravelRequests:new Set()};
      window.personalPrefs=()=>({default_travel:'transit',departure_buffer:5,arrival_buffer:10});
      window.eventStartAt=item=>item?.start_at?new Date(item.start_at):null;
      window.eventEndAt=item=>item?.end_at?new Date(item.end_at):null;
      window.safeColour=(value,fallback='#365CE6')=>value||fallback;
      window.escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
      window.appleDestinationLink=value=>escapeHtml(value);
      window.eventPlaceName=item=>item.location_name||item.title||'Event';
      window.eventViewAttributes=()=> '';
      window.postTravelSummary=()=> '';
      window.travelRouteStrip=()=> '';
      window.render=()=>{};
      window.routeCalls=[];
      window.api=async(path,options)=>{routeCalls.push({path,body:options.body});await new Promise(resolve=>setTimeout(resolve,20));throw new Error('The route provider is unavailable.');};
    `});
    const functions = [
      'todayLocationIdentity','sameTodayLocation','todayTimelineGroups','eventTravelKind',
      'todayPostTravelRequestKey','todayInboundKey','todayDurationHours','todayEventDurationLabel',
      'todayAreaIcon','renderTodayAppointment','todayInboundMarkup','todayTravelConnector',
      'renderTodayTimeline','ensureDailyPostTravel'
    ];
    await page.addScriptTag({content:functions.map(sourceFunction).join('\n')});
    await page.evaluate(() => {
      window.timelineItems=[
        {id:1,origin:'Shift',location_id:7,location_name:'Saved Workplace',location:'Workplace Road',
          start_at:'2030-10-01T08:00',end_at:'2030-10-01T12:00',hours:4,shift_type_name:'Shift A',
          shift_type_colour:'#16d5d0',location_colour:'#078ef0'},
        {id:2,origin:'Shift',location_id:7,location_name:'Saved Workplace',location:'Workplace Road',
          start_at:'2030-10-01T12:30',end_at:'2030-10-01T16:30',hours:4,shift_type_name:'Shift B',
          shift_type_colour:'#16d5d0',location_colour:'#078ef0'},
        {id:3,origin:'Event',section_id:1,title:'Personal appointment',location:'Clinic Road',
          start_at:'2030-10-01T17:15',end_at:'2030-10-01T18:00',notes:'Bring appointment notes'}
      ];
    });

    const model = await page.evaluate(() => ({
      topLevelCount:todayTimelineGroups(timelineItems).length,
      shiftGroupCount:todayTimelineGroups(timelineItems)[0].items.length,
      samePlace:todayLocationIdentity(timelineItems[0])===todayLocationIdentity(timelineItems[1]),
      latestFinishId:todayTimelineGroups([
        {...timelineItems[0],end_at:'2030-10-01T16:30'},
        {...timelineItems[1],start_at:'2030-10-01T12:30',end_at:'2030-10-01T15:00'}
      ])[0].last.id,
      inboundKeyBefore:todayInboundKey(timelineItems[0])
    }));
    assert.equal(model.topLevelCount,2);
    assert.equal(model.shiftGroupCount,2);
    assert.equal(model.samePlace,true);
    assert.equal(model.latestFinishId,1,'The workplace header should use the latest shift finish, not only the last shift start.');
    const updatedHomeKey = await page.evaluate(() => {
      state.boot.settings.user_address='Home Road Two';
      return todayInboundKey(timelineItems[0]);
    });
    assert.notEqual(updatedHomeKey,model.inboundKeyBefore,'Changing the saved home address should invalidate the inbound route cache.');

    await page.evaluate(async () => {
      const groups=todayTimelineGroups(timelineItems);
      await Promise.all([ensureDailyPostTravel(groups),ensureDailyPostTravel(groups)]);
      document.querySelector('#app').innerHTML=`<section class="page today-reference-page">
        <header class="today-reference-header"><div class="today-reference-date"><span aria-hidden="true">▦</span><h1>Tuesday schedule</h1></div>
          <div class="today-reference-total" role="group" aria-label="Daily schedule summary"><strong>2 Events</strong><span aria-hidden="true">·</span><strong>8h 45m scheduled</strong></div></header>
        <div class="today-event-timeline">${renderTodayTimeline(timelineItems)}</div></section>`;
    });

    assert.equal(await page.locator('.today-location-block').count(),1);
    assert.equal(await page.locator('.today-shift-area').count(),2);
    assert.equal(await page.locator('.today-appointment-card').count(),1);
    assert.equal(await page.locator('.today-inbound-travel').count(),1);
    assert.equal(await page.locator('.today-travel-connector').count(),1);
    assert.match(await page.locator('.today-location-header').innerText(),/08:00–16:30/);
    assert.match(await page.locator('.today-location-block').innerText(),/8 hours total · 2 shifts/);
    assert.match(await page.locator('.today-travel-connector').innerText(),/Route unavailable/);
    assert.equal(await page.evaluate(() => routeCalls.length),1,'Concurrent renders should reuse the in-flight route request.');

    await page.evaluate(async () => {
      timelineItems[2].location='Updated Clinic Road';
      await ensureDailyPostTravel(todayTimelineGroups(timelineItems));
    });
    assert.equal(await page.evaluate(() => routeCalls.length),2,'Changing the destination address should request a fresh route.');

    const mobileLayout = await page.evaluate(() => ({
      viewport:document.documentElement.clientWidth,
      pageWidth:document.documentElement.scrollWidth,
      cardRight:document.querySelector('.today-location-block').getBoundingClientRect().right,
      appointmentRight:document.querySelector('.today-appointment-card').getBoundingClientRect().right,
      workplaceBorder:getComputedStyle(document.querySelector('.today-location-block')).borderLeftWidth,
      shiftBorder:getComputedStyle(document.querySelector('.today-shift-area')).borderLeftWidth,
      travelBorder:getComputedStyle(document.querySelector('.today-travel-connector')).borderLeftWidth
    }));
    assert.ok(mobileLayout.pageWidth<=mobileLayout.viewport,`Mobile page overflows horizontally: ${JSON.stringify(mobileLayout)}`);
    assert.ok(mobileLayout.cardRight<=mobileLayout.viewport,`Workplace card exceeds viewport: ${JSON.stringify(mobileLayout)}`);
    assert.ok(mobileLayout.appointmentRight<=mobileLayout.viewport,`Appointment exceeds viewport: ${JSON.stringify(mobileLayout)}`);
    assert.equal(mobileLayout.workplaceBorder,'2px');
    assert.equal(mobileLayout.shiftBorder,'1px');
    assert.equal(mobileLayout.travelBorder,'1px');

    fs.mkdirSync(path.join(__dirname,'test-results'),{recursive:true});
    await page.screenshot({path:path.join(__dirname,'test-results','daily-timeline-mobile.png'),fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
    await page.screenshot({path:path.join(__dirname,'test-results','daily-timeline-desktop.png'),fullPage:true});
    console.log('Timeline UI regression passed at 390px mobile and 1440px desktop widths.');
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error=>{console.error(error);process.exitCode=1;});

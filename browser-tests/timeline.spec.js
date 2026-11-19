const { chromium, webkit, devices } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const appSource = fs.readFileSync(path.join(ROOT, 'static', 'app.js'), 'utf8');
const personalSource = fs.readFileSync(path.join(ROOT, 'static', 'personal-planner.js'), 'utf8');
const journeySource = fs.readFileSync(path.join(ROOT, 'static', 'journey-breakdown.js'), 'utf8');
const postTravelSource = fs.readFileSync(path.join(ROOT, 'static', 'post-event-travel.js'), 'utf8');
const styles = fs.readFileSync(path.join(ROOT, 'static', 'styles.css'), 'utf8');
const eventStyles = fs.readFileSync(path.join(ROOT, 'static', 'events-global.css'), 'utf8');

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
    const eventStyleTag=await page.addStyleTag({content:eventStyles});
    await page.addScriptTag({content:`
      window.state={boot:{personal:{journey_provider:'configured'},settings:{user_address:'Home Road One'}},tab:'today',
        dailyInboundJourneys:{},dailyInboundLoading:{},dailyInboundErrors:{},postTravelRequests:new Map()};
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
      'todayAreaIcon','renderTodayAppointment','todayHomeTravelMarkup','todayInboundMarkup','todayTravelConnector',
      'renderTodayTimeline','ensureDailyPostTravel','ensureTodayInboundTravel'
    ];
    await page.addScriptTag({content:functions.map(sourceFunction).join('\n')});
    const formFunctions = ['journeyBuffers','travelOptions','savedJourneyMode','eventTravelFields']
      .map(name => {
        const line = personalSource.split('\n').find(value => value.startsWith(`function ${name}(`));
        if (name === 'savedJourneyMode') return 'function savedJourneyMode(){return null;}';
        assert.ok(line, `Missing ${name}`);
        return line;
      });
    await page.addScriptTag({content:`window.isAdmin=true;const travelLabels={drive:'Driving',bus:'Bus',train:'Train',transit:'Bus and train'};\n${formFunctions.join('\n')}`});
    const eventForm = await page.evaluate(() => eventTravelFields());
    assert.match(eventForm,/name="departure_buffer"/);
    assert.doesNotMatch(eventForm,/arrival_buffer|early-arrival buffer/);
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
      await ensureTodayInboundTravel(timelineItems[0]);
    });
    const inboundRequest = await page.evaluate(() => routeCalls.shift());
    assert.equal(inboundRequest.body.arrival,'2030-10-01T08:00');
    assert.equal(inboundRequest.body.departure_buffer,5);
    assert.equal('arrival_buffer' in inboundRequest.body,false,'Today must use the event start, not an early-arrival buffer.');

    await page.addScriptTag({content: postTravelSource.slice(postTravelSource.indexOf('function condensedJourneyText'), postTravelSource.indexOf('function postTravelSummary'))});
    const inboundMarkup = await page.evaluate(() => {
      state.dailyInboundJourneys[todayInboundKey(timelineItems[0])]={leave_at:'2030-10-01T07:40',arrival_at:'2030-10-01T08:00',steps:[{mode:'bus',service:'414'}]};
      return todayInboundMarkup(timelineItems[0],true);
    });
    assert.match(inboundMarkup,/design-travel/,'Home travel uses the route strip.');
    assert.match(inboundMarkup,/Travel to/);
    assert.match(inboundMarkup,/Leave/);
    assert.match(inboundMarkup,/07:40/);
    assert.match(inboundMarkup,/Bus/);
    assert.match(inboundMarkup,/414/);
    assert.doesNotMatch(inboundMarkup,/journey-compact-item/);

    await page.addScriptTag({content:journeySource+'\n'+postTravelSource});
    await page.evaluate(() => {
      const journey={leave_at:'2030-10-01T07:55',arrival_at:'2030-10-01T08:30',steps:[
        {mode:'walk',minutes:4,start:'2030-10-01T08:00',end:'2030-10-01T08:04'},
        {mode:'bus',service:'414',start:'2030-10-01T08:04',end:'2030-10-01T08:15',from:'Stop A',to:'Stop B'},
        {mode:'wait',minutes:3,start:'2030-10-01T08:15',end:'2030-10-01T08:18'},
        {mode:'train',service:'Rail',platform:'2',start:'2030-10-01T08:18',end:'2030-10-01T08:27'},
        {mode:'walk',minutes:3,start:'2030-10-01T08:27',end:'2030-10-01T08:30'}
      ]};
      const strip=travelRouteStrip(journey,{detailed:true,leaveAtFirstWalk:true});
      document.querySelector('#app').innerHTML='<section class="today-inbound-travel">'+strip+'</section><section class="today-travel-connector"><div class="shift-travel-itinerary-wrap"><strong>Travel</strong>'+strip+'</div></section>';
    });
    const journeyItems=page.locator('.today-inbound-travel .journey-compact-item');
    assert.equal(await journeyItems.count(),7,'Every leg and both endpoints must remain visible.');
    assert.match(await journeyItems.nth(0).innerText(),/08:00/);
    assert.match(await journeyItems.nth(1).innerText(),/4 min/);
    assert.match(await journeyItems.nth(2).innerText(),/414 · 08:04/);
    assert.match(await journeyItems.nth(4).getAttribute('aria-label'),/Platform 2/);
    assert.match(await journeyItems.nth(6).innerText(),/08:30/);
    await page.locator('.today-inbound-travel .journey-compact-details summary').click();
    assert.match(await page.locator('.today-inbound-travel .journey-compact-details').innerText(),/Stop A → Stop B/);
    assert.equal(await page.locator('.today-travel-connector .journey-compact-item').count(),7);
    assert.equal(await page.locator('.today-travel-connector .shift-travel-arrow').first().evaluate(node=>getComputedStyle(node).display),'block');
    assert.equal(await page.locator('.today-travel-connector .journey-compact-strip').evaluate(node=>getComputedStyle(node).flexWrap),'wrap');
    assert.equal(await page.locator('.today-travel-connector .journey-compact-strip').evaluate(node=>getComputedStyle(node).overflowX),'visible');
    for (const width of [320,390,1440]) {
      await page.setViewportSize({width,height:844});
      const bounds=await page.evaluate(() => ({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
      assert.ok(bounds.scroll<=bounds.width,`Journey strip overflows at ${width}px: ${JSON.stringify(bounds)}`);
      for (let i=0;i<7;i++) assert.equal(await journeyItems.nth(i).isVisible(),true);
    }
    await page.setViewportSize({width:390,height:844});
    await page.locator('.today-inbound-travel .journey-compact-details summary').click();
    fs.mkdirSync(path.join(__dirname,'test-results'),{recursive:true});
    await page.screenshot({path:path.join(__dirname,'test-results','compact-route-mobile.png'),fullPage:true});
    await eventStyleTag.evaluate(node=>node.remove());

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
    assert.equal(await page.evaluate(() => routeCalls.length),2,'Concurrent renders should reuse both the next-event and final home requests.');

    await page.evaluate(async () => {
      timelineItems[2].location='Updated Clinic Road';
      await ensureDailyPostTravel(todayTimelineGroups(timelineItems));
    });
    assert.equal(await page.evaluate(() => routeCalls.length),4,'Changing the destination address should refresh both affected routes.');

    await page.evaluate(async () => {
      window.api=async()=>({journey:{leave_at:'2030-10-01T16:30',arrival_at:'2030-10-01T17:00',steps:[]}});
      const item={id:4,origin:'Event',location:'Clinic Road',start_at:'2030-10-01T16:00',end_at:'2030-10-01T16:30'};
      await ensureDailyPostTravel([{first:item,last:item}]);
      window.reloadedItem={...item};
      await ensureDailyPostTravel([{first:reloadedItem,last:reloadedItem}]);
    });
    const reusedTravel = await page.evaluate(() => reloadedItem.post_travel);
    assert.equal(reusedTravel.journey.arrival_at,'2030-10-01T17:00','A matching timeline result should be restored to newly decorated items.');
    assert.ok(reusedTravel.request_key);

    await page.evaluate(() => {
      const next=timelineItems[2], from=timelineItems[1];
      from.post_travel={timeline:true,enabled:true,request_key:todayPostTravelRequestKey(from,next),
        deadline:next.start_at,destination_name:'Appointment',journey:{leave_at:'2030-10-01T16:30',arrival_at:'2030-10-01T17:00',steps:[]}};
      next.post_travel={timeline:true,enabled:true,deadline:'',destination_name:'Home',
        journey:{leave_at:'2030-10-01T18:00',arrival_at:'2030-10-01T18:30',steps:[]}};
      document.querySelector('#app').innerHTML=renderTodayTimeline(timelineItems);
    });
    const schedule=page.locator('#app');
    assert.equal(await schedule.locator('.today-travel-connector[aria-label="Travel to next event"]').count(),1);
    assert.equal(await schedule.locator('.today-home-travel').count(),1);
    assert.match(await schedule.locator('.today-appointment-card .today-home-travel').innerText(),/Travel home/);
    assert.equal(await schedule.locator(':scope > .today-travel-connector').count(),1);
    const nextTravel=schedule.locator('.today-travel-connector[aria-label="Travel to next event"]');
    assert.match(await nextTravel.innerText(),/Leave/);
    assert.match(await nextTravel.innerText(),/16:30/);
    assert.match(await nextTravel.innerText(),/Arrive/);
    assert.match(await nextTravel.innerText(),/17:00/);
    assert.equal(await nextTravel.locator('.journey-compact-strip').count(),0,'The next-event strip uses the design route, not the compact itinerary.');
    await page.evaluate(() => {
      const last=timelineItems[1];
      last.post_travel={enabled:true,deadline:'',destination_name:'Home',
        journey:{leave_at:'2030-10-01T16:30',arrival_at:'2030-10-01T17:00',steps:[]}};
      document.querySelector('#app').innerHTML=renderTodayTimeline(timelineItems.slice(0,2));
    });
    assert.equal(await schedule.locator('.today-location-block .today-home-travel').count(),1,'Final grouped shift keeps the home journey inside the location');
    const restoredCache=await page.evaluate(async () => {
      const item={id:99,origin:'Event',location:'Saved Road',start_at:'2030-10-01T14:00',end_at:'2030-10-01T15:00',
        post_travel:{timeline:true,deadline:'',journey:{leave_at:'2030-10-01T15:00',arrival_at:'2030-10-01T15:30',steps:[]}}};
      const before=routeCalls.length;
      await ensureDailyPostTravel([{first:item,last:item}]);
      return {requests:routeCalls.length-before,requestKey:item.post_travel.request_key};
    });
    assert.equal(restoredCache.requests,0,'A validated timeline journey should avoid a redundant request.');
    assert.ok(restoredCache.requestKey,'A restored timeline journey should be associated with its current request key.');
    const historicalCache=await page.evaluate(async () => {
      const from={id:98,origin:'Event',location:'Past Road',start_at:'2020-10-01T09:00',end_at:'2020-10-01T10:00',
        post_travel:{timeline:true,deadline:'2020-10-01T11:00',journey:{leave_at:'2020-10-01T10:00',arrival_at:'2020-10-01T10:30',steps:[]}}};
      const to={id:97,origin:'Event',location:'Past Clinic',start_at:'2020-10-01T11:00',end_at:'2020-10-01T12:00'};
      const before=routeCalls.length;
      await ensureDailyPostTravel([{first:from,last:from},{first:to,last:to}]);
      return {requests:routeCalls.length-before,requestKey:from.post_travel.request_key};
    });
    assert.equal(historicalCache.requests,0,'A saved journey should be retained after its departure time.');
    assert.ok(historicalCache.requestKey,'A historical journey should still be attached to its current timeline request.');
    const retainedResult=await page.evaluate(async () => {
      const item={id:100,origin:'Event',location:'Cached Road',start_at:'2030-10-01T14:00',end_at:'2030-10-01T15:00'};
      window.api=async(path,options)=>{routeCalls.push({path,body:options.body});return {destination_name:'Home',deadline:'',journey:{leave_at:'2030-10-01T15:00',arrival_at:'2030-10-01T15:30',steps:[]}};};
      await ensureDailyPostTravel([{first:item,last:item}]);
      const replacement={...item,post_travel:undefined};
      delete replacement._todayRouteRequestKey;
      await ensureDailyPostTravel([{first:replacement,last:replacement}]);
      return {requests:routeCalls.filter(call=>call.body?.id===100).length,journey:replacement.post_travel?.journey};
    });
    assert.equal(retainedResult.requests,1,'A successful request should be reused instead of only remembering its key.');
    assert.ok(retainedResult.journey,'A replacement timeline item should receive the retained journey result.');
    await page.evaluate(() => {
      timelineItems[2].start_at='2030-10-01T16:00';
      document.querySelector('#app').innerHTML=renderTodayTimeline(timelineItems);
    });
    assert.match(await schedule.locator(':scope > .today-travel-connector').innerText(),/overlap or leave no time/);
    await page.evaluate(() => {
      timelineItems[2].start_at='2030-10-01T17:15';
      document.querySelector('#app').innerHTML=renderTodayTimeline(timelineItems);
    });

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

    const locationGroup = await page.evaluate(() => {
      window.eventForecastChip = iso => `<span class="design-forecast">Weather ${String(iso).slice(11,16)}</span>`;
      const wards = {id:11,origin:'Shift',location_id:3,location_name:'Riverside Health Centre',location:'1 Example Lane, Test Town',
        latitude:53.1,longitude:-3.1,start_at:'2030-10-02T08:00',end_at:'2030-10-02T12:00',hours:4,
        shift_type_name:'Wards',shift_type_colour:'#2f9e8f',location_colour:'#078ef0'};
      const clinic = {id:12,origin:'Shift',location_id:9,location_name:'Riverside Health Centre',location:'Example Lane entrance, Test Town',
        latitude:53.4,longitude:-3.4,start_at:'2030-10-02T12:30',end_at:'2030-10-02T16:30',hours:4,
        shift_type_name:'Clinic',shift_type_colour:'#d17a32',location_colour:'#078ef0',
        post_travel:{timeline:true,enabled:true,deadline:'',destination_name:'Home',
          journey:{leave_at:'2030-10-02T16:30',arrival_at:'2030-10-02T17:00',steps:[{mode:'walk',minutes:12}]}}};
      const elsewhere = {id:13,origin:'Event',title:'Dentist',location:'4 Other Street, Test Town',location_name:'North Practice',
        start_at:'2030-10-02T18:00',end_at:'2030-10-02T18:30',section_colour:'#a76aff'};
      state.dailyInboundJourneys[todayInboundKey(wards)] = {leave_at:'2030-10-02T07:40',arrival_at:'2030-10-02T08:00',steps:[{mode:'walk',minutes:8}]};
      const samePlace = [wards, clinic];
      document.querySelector('#app').innerHTML = renderTodayTimeline(samePlace);
      const block = document.querySelector('.today-location-block');
      const areas = [...block.querySelectorAll('.today-shift-area')];
      const split = todayTimelineGroups([
        {...wards,id:21,end_at:'2030-10-02T10:00',hours:2,post_travel:undefined},
        {...elsewhere,id:22,start_at:'2030-10-02T11:00',end_at:'2030-10-02T12:00'},
        {...clinic,id:23,start_at:'2030-10-02T13:00',end_at:'2030-10-02T16:00',hours:3}
      ]);
      const nextDay = todayTimelineGroups([wards,{...clinic,id:24,start_at:'2030-10-03T09:00',end_at:'2030-10-03T12:00'}]);
      const calendarPair = todayTimelineGroups([
        {id:31,origin:'Calendar',title:'Wards',location:'1 Example Lane, Test Town',start_at:'2030-10-04T08:00',end_at:'2030-10-04T12:00',section_colour:'#2f9e8f',hours:4},
        {id:32,origin:'Calendar',title:'Clinic',location:'1 Example Lane, Test Town',start_at:'2030-10-04T13:00',end_at:'2030-10-04T16:30',section_colour:'#d17a32',hours:3.5}
      ]);
      return {
        groups:todayTimelineGroups(samePlace).length,
        names:areas.map(node=>node.querySelector('.today-area-name').textContent),
        colours:areas.map(node=>node.style.getPropertyValue('--area-colour')),
        times:areas.map(node=>node.querySelector('.today-area-time').textContent),
        durations:areas.map(node=>node.querySelector('.today-area-duration').textContent),
        weather:areas.map(node=>node.querySelector('.design-forecast')?.textContent||''),
        icons:areas.map(node=>node.querySelector('.today-area-icon svg')?.outerHTML||''),
        inbound:block.querySelectorAll('.today-inbound-travel').length,
        inboundLabel:block.querySelector('.today-inbound-travel')?.innerText||'',
        home:block.querySelectorAll('.today-home-travel').length,
        homeLabel:block.querySelector('.today-home-travel')?.innerText||'',
        travelInsideAreas:block.querySelectorAll('.today-location-areas .today-travel-connector, .today-location-areas .today-inbound-travel').length,
        header:block.querySelector('.today-location-header').innerText,
        splitCounts:split.map(group=>group.items.length),
        nextDayGroups:nextDay.length,
        calendarGroups:calendarPair.length,
        calendarItems:calendarPair[0]?.items.length||0
      };
    });
    assert.equal(locationGroup.groups,1,'Contiguous shifts at the same named place form one location block.');
    assert.deepEqual(locationGroup.names,['Wards','Clinic']);
    assert.notEqual(locationGroup.colours[0],locationGroup.colours[1]);
    assert.deepEqual(locationGroup.times,['08:00–12:00','12:30–16:30']);
    assert.deepEqual(locationGroup.durations,['4h','4h']);
    assert.deepEqual(locationGroup.weather,['Weather 08:00','Weather 12:30']);
    assert.notEqual(locationGroup.icons[0],locationGroup.icons[1],'Each area keeps its own icon.');
    assert.equal(locationGroup.inbound,1);
    assert.match(locationGroup.inboundLabel,/Travel to Riverside Health Centre/);
    assert.match(locationGroup.inboundLabel,/8 min/);
    assert.equal(locationGroup.home,1);
    assert.match(locationGroup.homeLabel,/Travel home/);
    assert.match(locationGroup.homeLabel,/12 min/);
    assert.equal(locationGroup.travelInsideAreas,0,'Items in one location block do not get a journey between them.');
    assert.match(locationGroup.header,/Riverside Health Centre/);
    assert.match(locationGroup.header,/1 Example Lane, Test Town/);
    assert.match(locationGroup.header,/08:00–16:30/);
    assert.match(locationGroup.header,/8 hours total · 2 shifts/);
    assert.deepEqual(locationGroup.splitCounts,[1,1,1],'A different place between two visits keeps them separate.');
    assert.equal(locationGroup.nextDayGroups,2,'The same place on another day stays a separate block.');
    assert.equal(locationGroup.calendarGroups,1);
    assert.equal(locationGroup.calendarItems,2,'Calendar items at the same address use the same location block.');
    console.log('Timeline UI regression passed at 390px mobile and 1440px desktop widths.');
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error=>{console.error(error);process.exitCode=1;});

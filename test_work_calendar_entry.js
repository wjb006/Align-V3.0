const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('static/app.js','utf8');
const start=source.indexOf('function renderSectionsIndex() {');
const end=source.indexOf('\nfunction installPanel()',start);
assert(start>=0&&end>start,'Sections renderer must exist');
const context={state:{sectionDefinitions:[]},escapeHtml:value=>String(value??''),callOptional:()=>''};
vm.createContext(context);
vm.runInContext(source.slice(start,end),context);

let html=context.renderSectionsIndex();
assert(html.includes('data-action="work-rota"'),'Unconfigured Work must offer rota upload');
assert(html.includes('data-action="work-setup"'),'Unconfigured Work must offer work details setup');
assert(html.includes('data-action="work-add-shifts"'),'Unconfigured Work must offer manual shift entry');
assert(html.includes('Work Calendar'),'Unconfigured Work must have a clear setup entry');

context.state.sectionDefinitions=[{key:'work',optional:true,enabled:false,name:'Work'}];
html=context.renderSectionsIndex();
assert(html.includes('data-action="work-rota"'),'Disabled Work must still offer rota upload');
assert(html.includes('data-action="work-setup"'),'Disabled Work must still offer work details setup');

context.state.sectionDefinitions=[{key:'work',optional:true,enabled:true,name:'Work',icon:'▣',colour:'#123456'}];
html=context.renderSectionsIndex();
assert(html.includes('data-action="work-setup"'),'Enabled Work must offer management settings');
assert(html.includes('data-action="work-add-shifts"'),'Enabled Work must offer manual shift entry');
assert(html.includes('data-action="work-rota"'),'Enabled Work must offer rota upload');
assert(!html.includes('data-action="work-opt-in"'),'Enabled Work must not ask the user to opt in again');
console.log('Work Calendar setup and management entry points passed');

// The restored planner must filter a second booking to the unused AM/PM period,
// count shifts and calendar events together, and surface saved shift travel.
const plannerSource=fs.readFileSync('static/shift-planner.js','utf8');
const plannerContext={
  state:{
    plannerMode:'month',plannerAnchor:'2026-11-01',shiftPlannerSelectedDay:'2026-11-09',tab:'planner',shiftPlannerModal:'add',
    shiftPlannerData:{
      start:'2026-11-01',end:'2026-11-30',
      shifts:[{id:11,work_date:'2026-11-09',start_time:'08:30',end_time:'12:30',location_name:'Arrowe Park',shift_type_name:'Clinic',hours:4,colour:'#123456',post_travel:{enabled:true,destination_name:'Clatterbridge',journey:{notes:'Leave at 12:30'}}}],
      templates:[
        {id:1,active:1,label:'AM Clinic',location_id:1,shift_type_id:1,location_name:'Arrowe Park',start_time:'08:30',end_time:'12:30'},
        {id:2,active:1,label:'PM Clinic',location_id:1,shift_type_id:1,location_name:'Arrowe Park',start_time:'13:00',end_time:'17:00'}
      ],
      locations:[{id:1,name:'Arrowe Park'}],shift_types:[{id:1,name:'Clinic'}],
      annual_leave:[],events:[{id:21,title:'Appointment',start_at:'2026-11-09T18:00',end_at:'2026-11-09T18:30'}],
      imported_events:[],finance_events:[],finance_calendar:{visible:true},work_settings:{}
    },boot:{settings:{}}
  },
  escapeHtml:v=>String(v??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])),
  api:async()=>({}),document:{addEventListener:()=>{},querySelector:()=>null},
  window:{},postTravelSummary:item=>item?.post_travel?.journey?'<details>Travel to Clatterbridge</details>':'',
  eventTravelMarkup:item=>item?.post_travel?.journey?'<details>Travel to Clatterbridge</details>':'',
  setTimeout:()=>0,console
};
vm.createContext(plannerContext);
vm.runInContext(plannerSource,plannerContext);
const plannerHtml=plannerContext.window.renderShiftPlanner();
assert(plannerHtml.includes('data-period="PM"'),'An AM shift already booked must default the form to PM');
assert(plannerHtml.includes('data-shift-type-label>PM shift type')&&plannerHtml.includes('data-shift-template-label>PM shift pattern'),'The form must offer PM controls when AM is already booked');
assert(plannerHtml.includes('data-shift-action="upload-rota"'),'Manual shift entry must offer the existing rota reader');
const dayInputs=plannerHtml.match(/<input type="checkbox" name="selected_days"[^>]*>/g)||[];
assert.equal(dayInputs.length,7,'Add shifts must display all seven days');
assert(dayInputs.every(input=>!input.includes('checked')),'Add shifts must not preselect a day');
assert(plannerHtml.includes('2 total items'),'The month cell must count the shift and calendar event together');
assert(plannerHtml.includes('Travel to Clatterbridge'),'Saved onward travel must appear on the shift card');
assert.equal((plannerHtml.match(/Travel to Clatterbridge/g)||[]).length,1,'Shift travel must not be repeated underneath its location group');
assert(!plannerHtml.includes('planner-location-travel'),'Shift travel stays inside the shift card');
plannerContext.state.shiftPlannerData.shifts=[];
plannerContext.state.shiftPlannerData.events=[{id:21,title:'Appointment',section_name:'Health',section_id:1,location:'Clinic Road',
  start_at:'2026-11-09T18:00',end_at:'2026-11-09T18:30',post_travel:{enabled:true,journey:{notes:'Travel home'}}}];
const eventHtml=plannerContext.window.renderShiftPlanner();
assert.equal((eventHtml.match(/Travel to Clatterbridge/g)||[]).length,1,'Event travel must appear once inside the event card');
assert(eventHtml.indexOf('Travel to Clatterbridge')<eventHtml.indexOf('</article>'),'Event travel must be inside its card');
assert(!eventHtml.includes('planner-location-travel'),'Event travel must not repeat underneath the location group');
plannerContext.state.shiftPlannerData.shifts=[
  {id:11,work_date:'2026-11-09',start_time:'08:00',end_time:'12:00',location_name:'Work',location:'Work Road',location_id:1,shift_type_name:'AM',hours:4},
  {id:12,work_date:'2026-11-09',start_time:'12:30',end_time:'16:30',location_name:'Work',location:'Work Road',location_id:1,shift_type_name:'PM',hours:4,
   post_travel:{enabled:true,deadline:'2026-11-09T17:15',journey:{notes:'Travel to appointment'}}}
];
plannerContext.state.shiftPlannerData.events=[{id:21,title:'Appointment',section_name:'Health',section_id:1,location:'Clinic Road',
  start_at:'2026-11-09T17:15',end_at:'2026-11-09T18:00',post_travel:{enabled:true,journey:{notes:'Travel home'}}}];
const scheduleHtml=plannerContext.window.renderShiftPlanner();
assert.equal((scheduleHtml.match(/Travel to Clatterbridge/g)||[]).length,2,'Next-event travel and final home travel each render once');
const connector=scheduleHtml.indexOf('planner-location-travel');
assert(connector>scheduleHtml.indexOf('PM')&&connector<scheduleHtml.indexOf('Appointment'),'Journey to next event must be between schedule entries');
assert(scheduleHtml.lastIndexOf('Travel to Clatterbridge')>scheduleHtml.indexOf('Appointment'),'Home journey must stay in the final event');
plannerContext.state.shiftPlannerData.events[0].start_at='2026-11-09T16:00';
const overlappingHtml=plannerContext.window.renderShiftPlanner();
assert(!overlappingHtml.includes('planner-location-travel'),'An overlapping event must not produce a misleading inter-event block');
console.log('AM/PM filtering, combined calendar totals and shift travel UI passed');

(async()=>{
  const start=plannerSource.indexOf('async function loadInboundPlannerJourneys(data) {');
  const end=plannerSource.indexOf('\n  function selectedShifts()',start);
  assert(start>=0&&end>start,'Timeline route loader must exist');
  const day=new Date();
  day.setDate(day.getDate()+1);
  const tomorrow=[day.getFullYear(),String(day.getMonth()+1).padStart(2,'0'),String(day.getDate()).padStart(2,'0')].join('-');
  const requests=[];
  const timelineContext={
    state:{plannerMode:'week'},
    getToday:()=>tomorrow,
    plannerItemStart:item=>item.work_date+'T'+item.start_time,
    plannerItemEnd:item=>item.work_date+'T'+item.end_time,
    plannerLocationKey:item=>item.location,
    api:async(path,options)=>{requests.push({path,body:options.body});return path==='/api/personal/journey'?{notes:'Route'}:{};},
    Date
  };
  vm.createContext(timelineContext);
  const load=vm.runInContext(plannerSource.slice(start,end)+';loadInboundPlannerJourneys',timelineContext);
  await load({shifts:[
    {id:1,work_date:tomorrow,start_time:'08:00',end_time:'09:00',location:'First Site'},
    {id:2,work_date:tomorrow,start_time:'13:00',end_time:'14:00',location:'Second Site'}
  ]});
  assert.equal(requests.filter(request=>request.path==='/api/personal/journey').length,1,'Only the first located group should receive a home-origin route.');
})().catch(error=>{console.error(error);process.exitCode=1;});

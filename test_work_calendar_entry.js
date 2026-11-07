const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('static/app.js','utf8');
const start=source.indexOf('function renderSectionsIndex() {');
const end=source.indexOf('\nfunction installPanel()',start);
assert(start>=0&&end>start,'Sections renderer must exist');
const context={state:{sectionDefinitions:[]},escapeHtml:value=>String(value??''),callOptional:()=>''};
vm.createContext(context);
vm.runInContext(source.slice(start,end),context);

let html=context.renderSectionsIndex();
assert(html.includes('data-action="work-opt-in"'),'Unconfigured Work must offer database opt-in');
assert(html.includes('Set up Work Calendar'),'Unconfigured Work must have a clear setup entry');
assert(!html.includes('data-action="work-setup"'),'Unconfigured Work must not skip the database opt-in step');

context.state.sectionDefinitions=[{key:'work',optional:true,enabled:false,name:'Work'}];
html=context.renderSectionsIndex();
assert(html.includes('data-action="work-opt-in"'),'Disabled Work must still offer opt-in');

context.state.sectionDefinitions=[{key:'work',optional:true,enabled:true,name:'Work',icon:'▣',colour:'#123456'}];
html=context.renderSectionsIndex();
assert(html.includes('data-action="work-setup"'),'Enabled Work must offer management settings');
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
  window:{},eventTravelMarkup:()=>'<details>Travel to Clatterbridge</details>',
  setTimeout:()=>0,console
};
vm.createContext(plannerContext);
vm.runInContext(plannerSource,plannerContext);
const plannerHtml=plannerContext.window.renderShiftPlanner();
assert(plannerHtml.includes('value="2"'),'An AM shift already booked must leave the PM pattern available');
assert(!plannerHtml.includes('value="1"'),'An AM shift already booked must hide other AM patterns');
assert(plannerHtml.includes('2 total items'),'The month cell must count the shift and calendar event together');
assert(plannerHtml.includes('Travel to Clatterbridge'),'Saved onward travel must appear on the shift card');
console.log('AM/PM filtering, combined calendar totals and shift travel UI passed');

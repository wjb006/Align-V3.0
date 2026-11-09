const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context={document:{addEventListener(){}},setInterval(){},personalPrefs:()=>({default_travel:'transit'}),escapeHtml:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),Date};
vm.createContext(context);vm.runInContext(fs.readFileSync('static/post-event-travel.js','utf8'),context);
assert.equal(context.upcomingNow({end_at:new Date(Date.now()-1000).toISOString()}),false);
assert.equal(context.upcomingNow({end_at:new Date(Date.now()+60000).toISOString()}),true);
const fields=context.postTravelFields({enabled:true,mode:'drive'});
assert.match(fields,/name="show_post_travel" checked/);
assert.match(fields,/<option value="drive" selected>/);
assert.equal(context.postTravelSummary({post_travel:{enabled:false}}),'');
const summary=context.postTravelSummary({post_travel:{enabled:true,destination_name:'<Home>',journey:{notes:'<script>unsafe</script>'}}});
assert.ok(!summary.includes('<script>'));assert.match(summary,/&lt;Home&gt;/);
assert.equal(context.postTravelSummary({post_travel:{enabled:true,destination_name:'Next'}}),'');
console.log('Post-event UI: expiry, saved preference, mode, safe display and stale journey checks passed.');

const strip=context.travelRouteStrip({leave_at:'2026-11-09T07:05',arrival_at:'2026-11-09T07:31',steps:[{mode:'walk',minutes:5},{mode:'bus',minutes:18,service_number:'410'},{mode:'walk',minutes:3}]});
assert.match(strip,/5 min/);
assert.match(strip,/18 min/);
const outbound=context.postTravelSummary({location:'Arrowe Park Hospital',post_travel:{enabled:true,origin:'Arrowe Park Hospital',destination:'Arrowe Park Medical Centre',destination_name:'Arrowe Park Medical Centre',deadline:'2026-11-09T17:15',journey:{leave_at:'2026-11-09T16:30',arrival_at:'2026-11-09T16:46',steps:[{mode:'walk',minutes:4},{mode:'bus',minutes:12,service_number:'472'}]}}});
assert.match(outbound,/Travel to next event/);
assert.match(outbound,/Arrowe Park Hospital/);

const inbound={leave_at:'2030-01-02T08:04',arrival_at:'2030-01-02T08:44',steps:[
  {mode:'walk',start:'2030-01-02T08:09',end:'2030-01-02T08:13'},
  {mode:'bus',service_number:'414',start:'2030-01-02T08:13',end:'2030-01-02T08:27'},
  {mode:'walk',start:'2030-01-02T08:27',end:'2030-01-02T08:44'},
]};
const actual=context.travelRouteStrip(inbound,{detailed:true,leaveAtFirstWalk:true});
assert.match(actual,/Leave, 08:09/);
assert.doesNotMatch(actual,/Leave, 08:04/);
assert.match(actual,/Bus, 414, 414 · 08:13, 08:13–08:27/);
assert.match(actual,/>4 min<\/strong>/);
assert.match(actual,/>414 · 08:13<\/strong>/);
assert.match(actual,/Arrive, 08:44/);
assert.match(context.travelRouteStrip(inbound,{detailed:true}),/Leave, 08:04/);
assert.match(context.travelRouteStrip({...inbound,steps:[]},{detailed:true,leaveAtFirstWalk:true}),/Leave, 08:04/);
const transfers=context.travelRouteStrip({leave_at:'2030-01-02T08:00',arrival_at:'2030-01-02T08:30',steps:[
  {mode:'walk',minutes:4},{mode:'bus',service:'<414>',start:'2030-01-02T08:04',end:'2030-01-02T08:12',from:'Stop A',to:'Stop B'},
  {mode:'wait',minutes:3},{mode:'train',service:'West',platform:'2',start:'2030-01-02T08:15',end:'2030-01-02T08:25'},
  {mode:'walk',minutes:5}
]},{detailed:true});
assert.equal((transfers.match(/role="listitem"/g)||[]).length,7);
assert.match(transfers,/&lt;414&gt; · 08:04/);
assert.match(transfers,/Stop A, Stop B/);
assert.match(transfers,/Connection, Connection|Connection, 3 min/);
assert.match(transfers,/West · 08:15/);
assert.match(transfers,/Platform 2/);

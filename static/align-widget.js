// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: yellow; icon-glyph: magic; share-sheet-inputs: url;
// Align V3.0 — Scriptable Home Screen events widget, v1.4
// Sign in through a secure prompt. Passwords and session tokens are not saved.
// Run in Scriptable to update the snapshot. Widgets use saved data only.
const BASE = 'https://beta.getalign.co.uk';
const fm = FileManager.local();
const savedFile = fm.joinPath(fm.libraryDirectory(), 'align-widget-v1.json');
const settingsFile = fm.joinPath(fm.libraryDirectory(), 'align-widget-settings.json');
const DEFAULTS = {view:'next',maxEvents:5,showLocation:true,showEndTime:true};
function preferences() {
  let saved={}; try { saved=JSON.parse(fm.readString(settingsFile)); } catch (_) {}
  const p={...DEFAULTS,...saved};
  if (!['next','today','3days','week'].includes(p.view)) p.view='next';
  p.maxEvents=Math.min(7,Math.max(1,parseInt(p.maxEvents,10)||5));
  return p;
}
async function configure() {
  const p=preferences();
  while(true) {
    const a=new Alert();a.title='Widget display';a.message='Settings apply to all Align widgets. A widget Parameter overrides the default view.';
    a.addAction('Default view: '+p.view);a.addAction('Maximum events: '+p.maxEvents);
    const fields=[['showLocation','Location'],['showEndTime','End time']];
    fields.forEach(([key,label])=>a.addAction(label+': '+(p[key]?'On':'Off')));a.addCancelAction('Save and close');
    const choice=await a.presentSheet();
    if(choice<0){fm.writeString(settingsFile,JSON.stringify(p));return;}
    if(choice===0){const views=['next','today','3days','week'];p.view=views[(views.indexOf(p.view)+1)%views.length];}
    else if(choice===1)p.maxEvents=p.maxEvents%7+1;
    else p[fields[choice-2][0]]=!p[fields[choice-2][0]];
  }
}
function readSaved() {
  try { return JSON.parse(fm.readString(savedFile)); } catch (_) { return null; }
}
function clearSaved() { if (fm.fileExists(savedFile)) fm.remove(savedFile); }
async function message(title, text) {
  const a = new Alert(); a.title = title; a.message = text; a.addAction('OK'); await a.presentAlert();
}
// Native requests avoid suspended WebView callbacks and service-worker caching.
async function apiRequest(path, cookie='', payload=null) {
  const request = new Request(BASE+path);
  request.timeoutInterval = 20;
  request.onRedirect = () => null;
  request.headers = {'Accept':'application/json', 'Cache-Control':'no-store', 'Origin':BASE};
  if (cookie) request.headers.Cookie = cookie;
  if (payload) { request.method='POST'; request.headers['Content-Type']='application/json'; request.body=JSON.stringify(payload); }
  let timer;
  try {
    const text = await Promise.race([
      request.loadString(),
      new Promise((_,reject) => { timer=Timer.schedule(25000,false,()=>reject(Error('Align took too long to respond. Try again shortly.'))); })
    ]);
    const status=request.response?.statusCode;
    if (status===401) throw Error('Sign-in expired or details were incorrect. Please try again.');
    if (status===403) throw Error('Access is not available. Open Align in Safari to check your account and accept any required terms.');
    if (status===429) throw Error('Too many sign-in attempts. Wait before trying again.');
    if (status!==200) throw Error('Align could not complete the request. Try again shortly.');
    let data;
    try { data=JSON.parse(text); } catch (_) { throw Error('Align returned a sign-in page instead of data. Check your account in Safari.'); }
    return {data, response:request.response};
  } finally {
    if (timer) timer.invalidate();
    request.body=null;
  }
}
async function updateSchedule() {
  const prompt=new Alert(); prompt.title='Sign in to Align';
  prompt.message='Your details are sent only to the configured Align host over HTTPS. This script does not save your password. No browser window is needed.';
  prompt.addTextField('Email'); prompt.addSecureTextField('Password');
  prompt.addAction('Sign in and save events'); prompt.addCancelAction('Cancel');
  if (await prompt.presentAlert()===-1) return false;
  const credentials={email:prompt.textFieldValue(0).trim(),password:prompt.textFieldValue(1)};
  let cookie='';
  try {
    let login;
    try { login=await apiRequest('/api/beta/login','',credentials); }
    finally { credentials.password=''; }
    const session=(login.response.cookies || []).find(c=>c.name==='align_beta');
    if (!session?.value || !/^[A-Za-z0-9._~-]+$/.test(session.value)) throw Error('Align did not return a usable session. Please try again.');
    cookie='align_beta='+session.value;
    // Validate the new account/feed before replacing any previously saved snapshot.
    const {data:b}=await apiRequest('/api/bootstrap',cookie);
    if (!b.beta || !/^\d{4}-\d{2}-\d{2}$/.test(b.dashboard?.today || '')) throw Error('Complete account setup in Safari first.');
    const rows=b.dashboard?.upcoming_events;
    if (!Array.isArray(rows)) throw Error('This Align host does not provide the V3 event feed yet. Update the widget after V3 is deployed.');
    clearSaved();
    const events=rows.map(x=>{
      const start=String(x.start_at||'');
      const end=String(x.end_at||'');
      if (!/^\d{4}-\d{2}-\d{2}T/.test(start) || !/^\d{4}-\d{2}-\d{2}T/.test(end)) return null;
      return {id:String(x.id),day:start.slice(0,10),start:start.slice(11,16),end:end.slice(11,16),
        location:String(x.location||''),title:String(x.title||'Event'),allDay:!!x.all_day};
    }).filter(Boolean);
    fm.writeString(savedFile,JSON.stringify({updated:new Date().toISOString(),events}));
    return true;
  } finally {
    credentials.password='';
    // Revoke only the session created by this script; other devices stay signed in.
    if (cookie) { try { await apiRequest('/api/beta/logout',cookie,{}); } catch (_) {} }
    cookie='';
  }
}

function widgetDate(iso) {
  const match = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? match[3] + '/' + match[2] + '/' + match[1] : String(iso || '');
}
function ukClock(date) {
  const f = new DateFormatter(); f.locale = 'en_GB'; f.timeZone = 'Europe/London'; f.dateFormat = 'yyyy-MM-dd HH:mm';
  return f.string(date);
}
function eventEnd(e) {
  if (e.allDay || e.end > e.start) return e.day+' '+e.end;
  const next = new Date(e.day+'T12:00:00Z'); next.setUTCDate(next.getUTCDate()+1);
  return next.toISOString().slice(0,10)+' '+e.end;
}
function nextEvent(snapshot, now) {
  return (snapshot?.events || []).filter(e => /^\d{4}-\d{2}-\d{2}$/.test(e.day) && eventEnd(e) > ukClock(now))
    .sort((a,b) => (a.day+' '+a.start).localeCompare(b.day+' '+b.start))[0];
}
function viewEvents(snapshot,now,view) {
  const today=ukClock(now).slice(0,10);
  const end=new Date(today+'T12:00:00Z');end.setUTCDate(end.getUTCDate()+({today:1,'3days':3,week:7}[view]||1));
  const until=end.toISOString().slice(0,10);
  const rows=(snapshot?.events||[]).filter(e=>/^\d{4}-\d{2}-\d{2}$/.test(e.day))
    .filter(e=>view==='next'?eventEnd(e)>ukClock(now):e.day<until&&eventEnd(e)>today+' 00:00')
    .sort((a,b)=>(a.day+' '+a.start).localeCompare(b.day+' '+b.start));
  return view==='next'?rows.slice(0,1):rows;
}
function widget(snapshot, previewFamily) {
  const p=preferences(),parameter=String(args.widgetParameter||'').trim().toLowerCase();
  const valid=['next','today','3days','week'];
  const view=valid.includes(parameter)?parameter:p.view;
  const family=previewFamily||config.widgetFamily||'medium';
  const w = new ListWidget(); w.backgroundColor = new Color('#19295c'); w.setPadding(14,14,14,14);
  w.url = BASE; w.refreshAfterDate = new Date(Date.now()+15*60000);
  const add = (text, size, bold=false) => { const t=w.addText(text); t.font=bold?Font.boldSystemFont(size):Font.systemFont(size); t.textColor=Color.white(); t.lineLimit=2; return t; };
  add('ALIGN · '+({next:'NEXT EVENT',today:'TODAY','3days':'NEXT 3 DAYS',week:'NEXT 7 DAYS'}[view]), 11, true); w.addSpacer(6);
  const rows=viewEvents(snapshot,new Date(),view);
  const capacity=family==='small'?1:family==='large'?6:2;
  const shown=rows.slice(0,Math.min(capacity,p.maxEvents));
  for (const event of shown) {
    const clock=event.allDay?'All day':event.start+(p.showEndTime?'–'+event.end:'');
    const title=add(widgetDate(event.day)+'  '+clock, family==='small'?15:12,true);title.lineLimit=1;
    const heading=[event.title,p.showLocation&&event.location].filter(Boolean).join(' · ');
    if(heading){const t=add(heading,12);t.lineLimit=2;}
    w.addSpacer(5);
  }
  if(!shown.length)add(snapshot?'No saved events in this view':'Run Align in Scriptable to set up.',13,true);
  if(rows.length>shown.length)add('+'+(rows.length-shown.length)+' more · open Align',10);
  w.addSpacer();
  if (snapshot) {
    const stale = Date.now()-new Date(snapshot.updated).getTime() > 86400000;
    const saved = ukClock(new Date(snapshot.updated));
    add(stale ? 'Old data · run script to update' : 'Saved '+widgetDate(saved.slice(0,10))+' '+saved.slice(11)+' UK', 9);
  }
  if(parameter&&!valid.includes(parameter))add('Use next, today, 3days or week',9);
  return w;
}

if (!config.runsInWidget) {
  const menu = new Alert(); menu.title='Align widget';
  menu.message='Save your Align events for the Home Screen widget. Updates are manual; tap the widget to open Align.';
  menu.addAction('Sign in / update schedule'); menu.addAction('Preview saved widget'); menu.addDestructiveAction('Clear saved schedule'); menu.addAction('Display settings'); menu.addCancelAction('Cancel');
  const choice=await menu.presentSheet();
  if (choice===0) {
    try {
      if (await updateSchedule()) await message('Events saved', 'Now add a Scriptable Home Screen widget and select this script. Run this script again when you want to refresh your events.');
    } catch (e) { await message('Update not completed', String(e.message || e)); }
  } else if (choice===2) { clearSaved(); await message('Events cleared', 'The widget will clear when iOS next redraws it. This does not sign you out of Align.'); }
  if(choice===3)await configure();
  if (choice!==-1) {
    const size=new Alert();size.title='Preview size';size.addAction('Small');size.addAction('Medium');size.addAction('Large');size.addCancelAction('Close');
    const selected=await size.presentSheet();
    if(selected>=0){const family=['small','medium','large'][selected],w=widget(readSaved(),family);if(selected===0)await w.presentSmall();else if(selected===1)await w.presentMedium();else await w.presentLarge();}
  }
} else { Script.setWidget(widget(readSaved())); }
Script.complete();



let relatedTravelBusy=false, relatedTravelRetry=null;
async function refreshRelatedTravel(){
 if(relatedTravelBusy||!navigator.onLine)return;
 clearTimeout(relatedTravelRetry);
 relatedTravelBusy=true;
 try{
  let status;
  do{
   status=await api('/api/personal/refresh-travel',{method:'POST',body:{}});
   if(!modalRoot.querySelector('form')){await refresh();if(state.sectionId)await reloadSection();}
  }while(status.ready>0);
  if(status.remaining)relatedTravelRetry=setTimeout(()=>refreshRelatedTravel(),300000);
 }catch(error){toast('Travel refresh is pending. Reopen Align to retry.');}
 finally{relatedTravelBusy=false;}
}
function travelNotesField(notes=''){
 return isAdmin?`<div class="field"><label>Notes</label><textarea name="notes" maxlength="20000">${escapeHtml(notes)}</textarea></div>`:`<input type="hidden" name="notes" value="${escapeHtml(notes)}">`;
}
/* Personal daily summary, quick capture and appointment planning. */
let personalWeather=null;
function homeWeatherChip(){
 const current=personalWeather?.current;
 if(!current)return weatherLoading?'<p class="home-weather-chip">Weather…</p>':'';
 const label=({0:'Clear',1:'Mainly clear',2:'Partly cloudy',3:'Overcast',45:'Fog',51:'Drizzle',61:'Light rain',63:'Rain',65:'Heavy rain',71:'Snow',80:'Showers',95:'Thunderstorm'}[Number(current.weather_code)])||'Weather';
 return `<p class="home-weather-chip">${escapeHtml(label)} ${escapeHtml(current.temperature_2m??'—')}°</p>`;
}
let weatherView='three', weatherDay='';

// EASY TO EDIT: weather freshness and location timeout (milliseconds).
function baseWeatherSettings(){return state.boot?.builder?.document?.base_structure?.weather||{};}
function weatherRefreshMs(){const minutes=Number(baseWeatherSettings().refresh_minutes)||15;return minutes*60*1000;}
const PHONE_LOCATION_TIMEOUT_MS = 10000;
let weatherCheckedAt=0, weatherLoading=false, weatherError='', weatherContext='', weatherRefreshTimer=0;
function phoneLocation(){
 return new Promise((resolve,reject)=>{
  if(!window.isSecureContext || !navigator.geolocation){reject(new Error('Phone location needs the secure HTTPS app address.'));return;}
  // Some browsers do not count a pending permission prompt towards their
  // geolocation timeout. Bound the whole operation so the saved town can load.
  let settled=false;
  const finish=(callback,value)=>{if(settled)return;settled=true;clearTimeout(timer);callback(value);};
  const unavailable=()=>finish(reject,new Error('Location unavailable. Allow location access or set a fallback weather town in Personal preferences.'));
  const timer=setTimeout(unavailable,PHONE_LOCATION_TIMEOUT_MS);
  try{
   navigator.geolocation.getCurrentPosition(p=>finish(resolve,{latitude:p.coords.latitude,longitude:p.coords.longitude}),unavailable,{enableHighAccuracy:false,timeout:PHONE_LOCATION_TIMEOUT_MS,maximumAge:60000});
  }catch(_){unavailable();}
 });
}
async function loadPersonalWeather(force=false){
 if(baseWeatherSettings().enabled===false)return;
 if(weatherLoading || (!force && Date.now()-weatherCheckedAt<weatherRefreshMs()))return;
 weatherLoading=true;weatherCheckedAt=Date.now();weatherError='';
 const context=weatherContext;
 try{
  let body;
  try{body=await phoneLocation();}catch(err){if(!personalPrefs().weather_town)throw err;body={};}
  const data=await api('/api/personal/weather',{method:'POST',body});
  if(context===weatherContext)personalWeather=data;
 }catch(err){if(context===weatherContext)weatherError=err.message;}
 finally{
  weatherLoading=false;
  if(context===weatherContext){
   window.clearTimeout(weatherRefreshTimer);
   weatherRefreshTimer=   window.setTimeout(()=>{if(['home','today'].includes(state.tab))void loadPersonalWeather();},weatherRefreshMs());
  }
  if(['home','today'].includes(state.tab))render();
 }
}

const personalPrefs=()=>state.boot?.personal?.preferences||{};
const travelLabels={drive:'Driving',bus:'Bus',train:'Train',transit:'Bus and train'};
function travelOptions(value){return Object.entries(travelLabels).map(([m,label])=>`<option value="${m}" ${value===m?'selected':''}>${label}</option>`).join('');}
function travelFields(){const p=personalPrefs();return `<fieldset><legend>How do you travel?</legend>${Object.entries(travelLabels).map(([m,label])=>`<label class="setup-check"><input type="checkbox" name="travel_modes" value="${m}" ${(p.travel_modes||['drive','bus']).includes(m)?'checked':''}>${label}</label>`).join('')}</fieldset><label class="field">Default travel method<select name="default_travel">${travelOptions(p.default_travel||'drive')}</select></label>`;}
function journeyBuffers(){const p=personalPrefs();return `<div class="form-grid two"><label class="field">Extra minutes before boarding<input type="number" name="departure_buffer" value="${p.departure_buffer??5}" min="0" max="120" required></label><label class="field">Arrive before event (minutes)<input type="number" name="arrival_buffer" value="${p.arrival_buffer??10}" min="0" max="120" required></label></div>`;}

function travelValues(form){return {travel_modes:[...form.querySelectorAll('[name=travel_modes]:checked')].map(e=>e.value),default_travel:form.elements.default_travel.value};}
function todayEventStillRelevant(event,today){
 if(!event?.start_at)return false;
 if(event.all_day)return event.start_at.slice(0,10)===today;
 if(!event.end_at)return event.start_at.slice(0,10)===today;
 const end=Date.parse(event.end_at);
 return Number.isFinite(end)?end>Date.now():event.start_at.slice(0,10)===today;
}
function personalToday(){
 const data=state.boot.personal;if(!data)return '';const p=data.preferences,e=escapeHtml;
 const showWeather=homeSectionContent('today','show_weather',true);
 const showSchedule=homeSectionContent('today','show_schedule',true);
 const showQuickAdd=homeSectionContent('today','show_quick_add',true);
 const context=JSON.stringify([state.boot.beta?.email||'',p.weather_town||'']);
 if(context!==weatherContext){weatherContext=context;personalWeather=null;weatherCheckedAt=0;weatherError='';weatherView='three';weatherDay='';window.clearTimeout(weatherRefreshTimer);}
 if(showWeather&&baseWeatherSettings().enabled!==false&&!weatherLoading&&Date.now()-weatherCheckedAt>=weatherRefreshMs())void loadPersonalWeather();
 const items=data.items.filter(i=>!i.done&&i.kind==='reminder'&&i.due_at.slice(0,10)<=data.today&&(p.include_overdue||i.due_at.slice(0,10)===data.today));
 const todayEvents=(data.events||[]).filter(event=>todayEventStillRelevant(event,data.today));
 const schedule=showSchedule?`<section class="today-schedule" aria-labelledby="today-schedule-heading">
       <div class="section-head"><h3 id="today-schedule-heading">Today’s Schedule</h3><button class="text-button" data-action="go-schedule">See calendar</button></div>
       <div class="today-event-list">${todayEvents.length?renderGroupedEventRows(todayEvents,{showDate:false,condensed:true,showLocation:false}):'<div class="card empty">Nothing else scheduled today.</div>'}</div>
     </section>`:'';
 const weather=showWeather?(baseWeatherSettings().enabled===false?'<p class="helper">Weather is disabled by the owner.</p>':`<div data-weather-result>${weatherMarkup(personalWeather,weatherError,weatherLoading,weatherLoading?'…':'↻')}</div>`):'';
 return `<section class="section today-glance-section" data-management-banner="today">
   <div class="section-head"><h2>${homeSectionTitle('today','Today at a glance')}</h2><button class="text-button" data-personal="preferences">Personal preferences</button></div>
   <div class="card today-glance-card">
     ${weather}
     ${schedule}
     ${p.show_todos?`<section class="today-todos"><h3>To do${p.include_overdue?' · due and overdue':''}</h3>${items.map(i=>`<p>${e(i.title)} <small>${e(formatDisplayDateTime(i.due_at))}</small> <button class="small-button" data-personal="done" data-id="${e(i.id)}">Complete</button></p>`).join('')||'<p>No unfinished reminders due.</p>'}</section>`:''}
   </div>
 </section>
 ${showQuickAdd?`<section class="section"><div class="section-head"><h2>Quick add</h2><button class="text-button" data-nav="inbox">Open Inbox</button></div><div class="quick-grid"><button class="quick-action" data-personal="note">＋ Note</button><button class="quick-action" data-personal="reminder">＋ Reminder</button><button class="quick-action" data-personal="event">＋ Event</button><button class="quick-action" data-personal="available">Find appointment times</button></div></section>`:''}`;
}
function weatherMarkup(w,error='',loading=false,refreshIcon='↻'){
 const e=escapeHtml;
 if(!w)return `<div class="today-weather-empty"><p>${e(error||(loading?'Getting weather for your location…':'Weather is not available yet.'))}</p><button type="button" class="icon-button today-weather-refresh" data-personal="weather" aria-label="Refresh weather" title="Refresh weather" ${loading?'disabled':''}>${refreshIcon}</button></div>`;
 const status=error
  ?`<p class="weather-status" role="alert">Refresh failed: ${e(error)}${w.stale?' Showing the saved forecast from the time below.':''}</p>`
  :w.stale?'<p class="weather-status" role="status">Showing a saved forecast while weather services recover. Align will retry automatically.</p>':'';
 const attribution=w.source==='MET Norway'?'<a href="https://www.met.no/en" target="_blank" rel="noopener">MET Norway</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0</a>':'<a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo</a>';
 const updated=`<small class="today-weather-updated">${w.stale?'Saved forecast':'Updated'} ${e(formatDisplayDateTime(w.checked_at,'Europe/London'))} · ${attribution}</small>`;
 const condition=code=>({0:['☀️','Clear'],1:['🌤️','Mainly clear'],2:['⛅','Partly cloudy'],3:['☁️','Overcast'],45:['🌫️','Fog'],48:['🌫️','Freezing fog'],51:['🌦️','Light drizzle'],53:['🌦️','Drizzle'],55:['🌧️','Heavy drizzle'],56:['🌧️','Freezing drizzle'],57:['🌧️','Freezing drizzle'],61:['🌦️','Light rain'],63:['🌧️','Rain'],65:['🌧️','Heavy rain'],66:['🌧️','Freezing rain'],67:['🌧️','Freezing rain'],71:['🌨️','Light snow'],73:['🌨️','Snow'],75:['❄️','Heavy snow'],77:['❄️','Snow grains'],80:['🌦️','Light showers'],81:['🌧️','Showers'],82:['🌧️','Heavy showers'],85:['🌨️','Snow showers'],86:['❄️','Heavy snow showers'],95:['⛈️','Thunderstorm'],96:['⛈️','Thunderstorm'],99:['⛈️','Thunderstorm']}[Number(code)]||['🌡️','Unknown']);
 const daily=w.daily?.time||[];
 const [todayIcon,todayLabel]=condition(w.current.weather_code);
 const todayCard=`<div class="today-weather-banner"><div class="today-weather-heading"><span class="weather-icon" aria-hidden="true">${todayIcon}</span><div><span class="eyebrow">Today’s weather</span><strong>${e(todayLabel)} · ${e(w.current.temperature_2m??'—')}°C</strong><span>High ${e(w.daily?.temperature_2m_max?.[0]??'—')}° · Low ${e(w.daily?.temperature_2m_min?.[0]??'—')}° · Rain ${w.daily?.precipitation_probability_max?.[0]==null?'—':e(w.daily.precipitation_probability_max[0])+'%'}</span></div></div><div class="today-weather-location"><div class="today-weather-place"><strong>${e(w.place)}</strong><button type="button" class="icon-button today-weather-refresh" data-personal="weather" aria-label="Refresh weather" title="Refresh weather" ${loading?'disabled':''}>${refreshIcon}</button></div>${updated}</div></div>`;
 const forecastCard=(day,index)=>{const [icon,label]=condition(w.daily.weather_code?.[index]);return `<article class="today-weather-day"><button type="button" data-personal="weather-day" data-date="${e(day)}" aria-label="Show weather summary for ${e(prettyDate(day,{weekday:'long',day:'numeric',month:'long'}))}"><strong>${e(prettyDate(day,{weekday:'short',day:'numeric',month:'short'}))}</strong><span>${icon} ${e(label)}</span><b>${e(w.daily.temperature_2m_min?.[index]??'—')}–${e(w.daily.temperature_2m_max?.[index]??'—')}°</b><small>Rain ${w.daily.precipitation_probability_max?.[index]==null?'—':e(w.daily.precipitation_probability_max[index])+'%'}</small></button></article>`;};
 let forecast='';
 if(weatherView==='hourly'){
  const hours=w.hourly?.time||[],temperatures=w.hourly?.temperature_2m||[],currentHour=String(w.current?.time||'').slice(0,13);
  let start=hours.findIndex(time=>String(time).slice(0,13)>=currentHour);
  if(start<0)start=0;
  forecast=hours.slice(start,start+24).map((time,offset)=>{const i=start+offset,[icon,label]=condition(w.hourly.weather_code?.[i]);return `<article class="weather-card"><strong>${e(String(time).slice(11,16))}</strong><div class="weather-card-heading"><span class="weather-icon" aria-hidden="true">${icon}</span><div><strong>${e(label)}</strong><span>${e(temperatures[i]??'—')}°C</span></div></div><small>Rain ${w.hourly.precipitation_probability?.[i]==null?'—':e(w.hourly.precipitation_probability[i])+'%'}</small></article>`;}).join('');
  forecast=forecast?`<div class="weather-cards" aria-label="Hourly forecast">${forecast}</div>`:'<p class="helper">Hourly forecast is not available.</p>';
 }else if(weatherView==='daily'){
  forecast=`<div class="today-weather-days">${daily.slice(0,7).map(forecastCard).join('')}</div>`;
 }else if(weatherView==='three'){
  forecast=`<div class="today-weather-next">${daily.slice(1,4).map((day,index)=>forecastCard(day,index+1)).join('')}</div>`;
 }else if(weatherView==='day'){
  const index=daily.indexOf(weatherDay||daily[0]);
  forecast=index>=0?`<div class="today-weather-days">${forecastCard(daily[index],index)}</div>`:'<p class="helper">That day’s forecast is not available.</p>';
 }
 return `<section class="today-weather" aria-label="Weather forecast">${weatherControls(w)}${todayCard}${forecast}${status}</section>`;
}
function weatherControls(w){
 const options=[['day','Today'],['hourly','Hourly'],['three','3 days'],['daily','7 days']];
 return `<div class="weather-view-switch" role="group" aria-label="Forecast view">${options.map(([view,label])=>`<button type="button" data-personal="weather-view" data-view="${view}" aria-pressed="${weatherView===view}">${label}</button>`).join('')}</div>`;
}
function personalPreferences(){const p=personalPrefs(),e=escapeHtml;modal('Personal preferences',`<form class="settings-form" data-personal-form="preferences">${travelFields()}${journeyBuffers()}<label class="field">Fallback weather town<input name="weather_town" value="${e(p.weather_town||'')}" placeholder="Town name"></label><fieldset><legend>Weather-aware travel</legend><label class="setup-check"><input name="weather_adjustments" type="checkbox" ${p.weather_adjustments!==false?'checked':''}>Allow extra leave time for heavy rain or storms</label><div class="form-grid two"><label class="field">Rain chance threshold (%)<input name="weather_rain_threshold" type="number" min="0" max="100" value="${p.weather_rain_threshold??50}"></label><label class="field">Rain buffer (minutes)<input name="weather_rain_buffer" type="number" min="0" max="60" value="${p.weather_rain_buffer??10}"></label><label class="field">Storm buffer (minutes)<input name="weather_storm_buffer" type="number" min="0" max="90" value="${p.weather_storm_buffer??15}"></label><label class="field">Traffic buffer cap (minutes)<input name="traffic_buffer_cap" type="number" min="0" max="120" value="${p.traffic_buffer_cap??30}"></label></div><p class="helper">Weather uses your rounded phone location or fallback town. HERE live traffic is used only when the server is configured; otherwise Align keeps fixed travel buffers.</p></fieldset><p class="helper">Weather loads automatically using your phone location, rounded to about 1 km before sharing with Open-Meteo or the MET Norway backup. The town is used if location is unavailable. Forecasts and a rounded-location cache key are stored privately; exact GPS is not saved.</p>${[['show_todos','Show to do items in Today'],['include_overdue','Include past missed, unfinished reminders']].map(([k,label])=>`<label class="setup-check"><input name="${k}" type="checkbox" ${p[k]?'checked':''}>${label}</label>`).join('')}<fieldset><legend>Event categories in Quick actions</legend><p class="helper">Leave all unchecked to offer every category.</p>${state.boot.sections.map(s=>`<label class="setup-check"><input type="checkbox" name="quick_categories" value="${s.id}" ${(p.quick_categories||[]).includes(s.id)?'checked':''}>${e(s.name)}</label>`).join('')}</fieldset><p class="helper">Automatic travel: ${state.boot.personal.routes_configured?'available':'awaiting owner service setup'}. OpenTripPlanner plans bus/train journeys from home by default. Include full UK postcodes. Only the postcode is sent to Postcodes.io; routing uses the configured OTP server. Postcode locations are approximate.</p><p role="alert" data-personal-error></p><button class="primary-button">Save preferences</button></form>`);}
function personalCapture(kind){const calendars=state.boot?.icloud_event_calendars||[];modal(kind==='note'?'Add note':'Add reminder',`<form class="settings-form" data-personal-form="capture" data-kind="${kind}" data-id="${crypto.randomUUID()}"><label class="field">${kind==='note'?'Note':'Reminder'}<textarea name="title" required maxlength="2000"></textarea></label>${kind==='reminder'?`<label class="field">Due date and time<input name="due_at" type="datetime-local" required></label><label class="field">Calendar<select name="calendar_id"><option value="">Align only</option>${calendars.map(c=>`<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)}</option>`).join('')}</select></label><p class="helper">Shown in Today and Inbox. The selected iCloud calendar will also receive this reminder as an event.</p><p class="helper">If phone notifications are enabled on this device, Align can deliver a private reminder that does not include this text.</p>`:''}<p role="alert" data-personal-error></p><button class="primary-button">Save</button></form>`);}
function personalItems(){modal('Notes & reminders',`<div class="settings-form">${state.boot.personal.items.map(i=>`<article class="card"><p>${escapeHtml(i.title)}</p><small>${i.kind==='note'?'Note':escapeHtml(formatDisplayDateTime(i.due_at))}${i.done?' · Complete':''}</small><div class="button-row">${i.kind==='reminder'?`<button class="small-button" data-personal="${i.done?'undo':'done'}" data-id="${i.id}">${i.done?'Reopen':'Complete'}</button>`:''}<button class="small-button" data-personal="delete" data-id="${i.id}">Delete</button></div></article>`).join('')||'<p>No notes or reminders yet.</p>'}</div>`);}
function personalEventPicker(slot=null){const selected=personalPrefs().quick_categories||[];const sections=state.boot.sections.filter(s=>!selected.length||selected.includes(s.id));modal('Choose event category',`<div class="quick-grid">${sections.map(s=>`<button class="quick-action" data-personal="category" data-id="${s.id}" data-start="${slot?.start_at||''}" data-end="${slot?.end_at||''}">${escapeHtml(s.icon)} ${escapeHtml(s.name)}</button>`).join('')||'<p>Add an event category first.</p>'}<button class="quick-action" data-action="new-section">＋ Create category</button></div>`);}
let availabilityView='week';
function personalAvailability(sectionId=null){modal('When are you free?',`<p>Choose an available time first, then add your event details.</p><form class="settings-form" data-personal-form="availability" data-section-id="${sectionId||''}"><label class="field">Search from<input type="date" name="date" value="${isoToday()}" required></label><div class="form-grid two"><label class="field">From<input type="time" name="start" value="08:00" required></label><label class="field">Until<input type="time" name="end" value="22:00" required></label><label class="field">Travel allowance each way (minutes)<input type="number" name="buffer" value="0" min="0" max="240" required></label><label class="field">Minimum free block (minutes)<input type="number" name="minimum_period" value="0" min="0" max="1440" step="15" required></label><label class="field">Day filter<select name="day_filter"><option value="all">All days</option><option value="weekdays">Weekdays</option><option value="weekend">Weekend</option></select></label></div><p class="helper">Shows continuous blocks of free time. Use the filters to hide short periods or restrict the list to weekdays/weekends.</p><p role="alert" data-personal-error></p><div class="button-row"><button class="primary-button">Find free periods</button><button type="button" class="secondary-button" data-personal="manual-event" data-section-id="${sectionId||''}">Choose my own time</button></div></form><div class="button-row"><button type="button" class="small-button" data-personal="free-view" data-view="week">Week view</button><button type="button" class="small-button" data-personal="free-view" data-view="month">Month view</button></div><div data-personal-slots aria-live="polite"></div>`);modalRoot.querySelector('[data-personal-form="availability"]').requestSubmit();}
async function createEventCalendar(form){const name=window.prompt('Name this iCloud calendar');if(!name?.trim())return;const result=await api('/api/icloud/create-event-calendar',{method:'POST',body:{name:name.trim()}});state.boot.icloud_event_calendars=result.event_calendars||await api('/api/bootstrap').then(data=>data.icloud_event_calendars||[]);if(form){const select=form.elements.calendar_id,option=document.createElement('option');option.value=result.created_calendar.id;option.textContent=result.created_calendar.name;select.insertBefore(option,select.querySelector('option[value="__create__"]'));select.value=option.value;}toast('Calendar created and ready for this event.');}
async function personalStartEvent(slot,sectionId){if(!sectionId){personalEventPicker(slot);return;}await openSection(Number(sectionId));sectionEventModal();if(slot){const f=modalRoot.querySelector('[data-form="organiser-event"]');f.elements.date.value=slot.start_at.slice(0,10);f.elements.start_time.value=slot.start_at.slice(11,16);f.elements.end_time.value=slot.end_at.slice(11,16);}}

function journeyFormSignature(f){return JSON.stringify(['date','start_time','location','journey_origin','journey_mode','departure_buffer','arrival_buffer'].map(n=>f.elements[n]?.value));}
function savedJourneyMode(notes){
 if(/Driving estimate:/i.test(notes))return 'drive';
 try {const steps=JSON.parse(notes.match(/\[Align travel steps\]([\s\S]*?)\[\/Align travel steps\]/i)?.[1]||'[]'),bus=steps.some(s=>s.mode==='bus'),train=steps.some(s=>s.mode==='train'||s.mode==='rail');return bus&&train?'transit':bus?'bus':train?'train':null;}catch(_){return null;}
}
function eventTravelFields(notes=''){return `<fieldset><legend>Travel</legend><label class="field">Start from<select name="journey_origin"><option value="home" selected>Home address</option><option value="phone">Current phone location</option></select></label><label class="field">Travel method<select name="journey_mode">${travelOptions(savedJourneyMode(notes)||personalPrefs().default_travel||'transit')}</select></label>${journeyBuffers()}<button type="button" class="small-button" data-personal="journey">Search journeys arriving in time</button><p class="helper">${state.boot?.personal?.journey_provider==='here'?'HERE uses your selected starting point and destination for address lookup and routing. Full addresses, postcodes and local station names are supported.':'OpenTripPlanner uses full postcodes or exact local station names. Postcode-centre walking times are approximate.'} Bus and train results use scheduled times; live delays are unavailable. Driving times are estimates.</p><p class="helper">Choose a journey to save its bus numbers, train services, stops, times and departure time with this event. Travel refreshes when its details change.</p><div role="status" data-journey-result></div><h3>Apple Maps</h3><div class="button-row"><button type="button" class="small-button" data-personal="apple-maps">Open in Apple Maps</button>${isAdmin?'<button type="button" class="small-button" data-personal="apple-notes">Add Apple Maps link to notes</button>':''}</div><p class="helper">Opens directions from your selected starting point to this event. In Apple Maps, choose Arrive by and set the event date/time, allowing for your early-arrival buffer. Check its bus numbers, train services, stops and walking directions. Apple Maps results are viewed there. Opening the link shares your selected starting point and destination with Apple.</p></fieldset>`;}
function addJourneyNotes(f,r){const old=f.elements.notes.value.replace(/\n?\[Align travel steps\][\s\S]*?\[\/Align travel steps\]/gi,'').replace(/\n?\[Align travel\][\s\S]*?\[\/Align travel\]/gi,'');const steps=r.steps?.length?`\n[Align travel steps]\n${JSON.stringify(r.steps)}\n[/Align travel steps]`:'';const notes=(old.trim()+'\n[Align travel]\n'+r.notes+'\n[/Align travel]'+steps).trim();if(notes.length>4000)throw new Error('Notes are too long. Shorten them before adding travel details.');f.elements.notes.value=notes;f.journeySignature=journeyFormSignature(f);f.querySelector('[data-journey-result]').textContent='Journey added. Leave '+r.leave_at.slice(11,16)+'. Save the event to keep these notes.';}

document.addEventListener('click',async ev=>{const b=ev.target.closest('[data-personal]');if(!b)return;const action=b.dataset.personal;try{
 if(action==='create-category-calendar'){const f=b.closest('form'),name=f.elements.name.value.trim();if(!name)throw new Error('Enter the category name first.');b.disabled=true;const r=await api('/api/icloud/create-calendar',{method:'POST',body:{name}});const option=document.createElement('option');option.value=r.created_calendar.id;option.textContent=r.created_calendar.name;f.elements.calendar_id.append(option);f.elements.calendar_id.value=option.value;toast('Calendar ready. Save the category to link it.');}
 if(action==='preferences')personalPreferences();
 if(action==='note'||action==='reminder')personalCapture(action);
 if(action==='new-event-calendar')await createEventCalendar(b.closest('[data-form="organiser-event"]'));
 if(action==='items')personalItems();
 if(action==='event')personalAvailability();
 if(action==='available')personalAvailability();
 if(action==='free-view'){availabilityView=b.dataset.view;const f=b.closest('.modal')?.querySelector('[data-personal-form="availability"]')||document.querySelector('[data-personal-form="availability"]');if(f)f.requestSubmit();}
 if(action==='slot')await personalStartEvent({start_at:b.dataset.start,end_at:b.dataset.end},b.dataset.sectionId);
 if(action==='manual-event')await personalStartEvent(null,b.dataset.sectionId);
 if(action==='category'){await openSection(Number(b.dataset.id));sectionEventModal();const f=document.querySelector('[data-form=organiser-event]');if(b.dataset.start){f.elements.date.value=b.dataset.start.slice(0,10);f.elements.start_time.value=b.dataset.start.slice(11,16);f.elements.end_time.value=b.dataset.end.slice(11,16);}}
 if(['done','undo','delete'].includes(action)){if(action==='delete'&&!confirm('Delete this item?'))return;await api('/api/personal/items/'+b.dataset.id,{method:action==='delete'?'DELETE':'PUT',body:{done:action==='done'}});await refresh();if(modalRoot.innerHTML)personalItems();}
 if(action==='weather'){b.disabled=true;await loadPersonalWeather(true);b.disabled=false;}
 if(action==='weather-view'){if(['day','hourly','three','daily'].includes(b.dataset.view)){weatherView=b.dataset.view;weatherDay='';render();}}
 if(action==='weather-day'){weatherView='day';weatherDay=b.dataset.date;render();}
 
 if(action==='apple-maps'||action==='apple-notes'){const f=b.closest('form');const position=f.elements.journey_origin.value==='phone'?await phoneLocation():null,home=position?position.latitude+','+position.longitude:state.boot.settings.user_address?.trim(),destination=f.elements.location.value.trim();if(!home||!destination)throw new Error('Add your home address in Personal details and the event location, or select phone location.');const url=appleDirectionsURL(home,destination,f.elements.journey_mode.value);if(action==='apple-maps'){window.location.assign(url);}else{const date=f.elements.date.value,time=f.elements.start_time.value,buffer=f.elements.arrival_buffer.value;const note='Apple Maps directions from selected starting point: '+url+'\nSet Arrive by for '+date+' at '+time+' (event time), minus '+buffer+' minutes for early arrival. Check walking time to the first stop/station and allow extra boarding time.\nApple Maps service details: ';const next=(f.elements.notes.value.trim()+'\n'+note).trim();if(next.length>4000)throw new Error('Shorten the notes before adding the Apple Maps link.');f.elements.notes.value=next;toast('Apple Maps link added. Enter any service details and save the event.');}}
 if(action==='use-journey'){const f=b.closest('form');addJourneyNotes(f,f.personalJourneys[Number(b.dataset.index)]);}
 if(action==='toggle-journeys'){const panel=b.nextElementSibling,expanded=b.getAttribute('aria-expanded')==='true';b.setAttribute('aria-expanded',String(!expanded));b.textContent=expanded?`Show more journeys (${panel.children.length})`:'Show fewer journeys';panel.hidden=expanded;}
 if(action==='journey'){const f=b.closest('form');if(f.elements.all_day.checked)throw new Error('Choose a timed event to calculate travel.');b.disabled=true;const r=await api('/api/personal/journey',{method:'POST',body:{...(f.elements.journey_origin.value==='phone'?await phoneLocation():{}),destination:f.elements.location.value,arrival:f.elements.date.value+'T'+f.elements.start_time.value,mode:f.elements.journey_mode.value,departure_buffer:Number(f.elements.departure_buffer.value),arrival_buffer:Number(f.elements.arrival_buffer.value)}});f.personalJourneys=r.journeys;f.querySelector('[data-journey-result]').innerHTML=r.journeys.map((j,i)=>`<article class="card"><h3>Leave ${escapeHtml(j.leave_at.slice(11,16))} · Arrive ${escapeHtml(j.arrival_at.slice(11,16))}</h3>${journeyBreakdown(j.steps||[])}<p style="white-space:pre-line">${escapeHtml(j.notes)}</p><button type="button" class="small-button" data-personal="use-journey" data-index="${i}">Use this journey</button></article>`).join('');}

 }catch(err){toast(err.message);}finally{b.disabled=false;}});

document.addEventListener('submit',async ev=>{const f=ev.target;if(!f.dataset.personalForm)return;ev.preventDefault();ev.stopImmediatePropagation();const b=f.querySelector('button.primary-button');b.disabled=true;try{const kind=f.dataset.personalForm;const values=Object.fromEntries(new FormData(f));
 if(kind==='preferences'){await api('/api/personal/preferences',{method:'PUT',body:{...travelValues(f),departure_buffer:Number(values.departure_buffer),arrival_buffer:Number(values.arrival_buffer),weather_town:values.weather_town,weather_adjustments:f.elements.weather_adjustments.checked,weather_rain_threshold:Number(values.weather_rain_threshold),weather_rain_buffer:Number(values.weather_rain_buffer),weather_storm_buffer:Number(values.weather_storm_buffer),traffic_buffer_cap:Number(values.traffic_buffer_cap),show_todos:f.elements.show_todos.checked,include_overdue:f.elements.include_overdue.checked,quick_categories:[...f.querySelectorAll('[name=quick_categories]:checked')].map(x=>Number(x.value))}});closeModal();await refresh();}
 if(kind==='capture'){await api('/api/personal/items',{method:'POST',body:{id:f.dataset.id,kind:f.dataset.kind,title:values.title,due_at:values.due_at||'',calendar_id:values.calendar_id||''}});closeModal();await refresh();toast('Saved.');}
 if(kind==='availability'){const target=modalRoot.querySelector('[data-personal-slots]');const count=availabilityView==='month'?35:7;const minimum=Number(values.minimum_period||0),filter=values.day_filter||'all';target.innerHTML=`<p>Checking your ${availabilityView} view…</p>`;const dates=Array.from({length:count},(_,i)=>{const d=new Date(values.date+'T12:00:00');d.setDate(d.getDate()+i);return toIso(d);});const results=await Promise.all(dates.map(date=>api('/api/personal/availability',{method:'POST',body:{...values,date}}).then(result=>({date,...result}))));if(f.isConnected){let first=true;target.innerHTML=results.map(r=>{const day=new Date(r.date+'T12:00:00').getDay();if(filter==='weekdays'&&(day===0||day===6)||filter==='weekend'&&day>0&&day<6)return '';const periods=(r.periods||[]).filter(s=>(new Date(s.end_at)-new Date(s.start_at))/60000>=minimum);const earliest=first&&periods.length;if(earliest)first=false;return `<section class="section"><h3>${escapeHtml(prettyDate(r.date,{weekday:'long',day:'numeric',month:'short'}))}${earliest?' · Next free':''}</h3><div class="quick-grid">${periods.map(s=>`<button type="button" class="small-button" data-personal="slot" data-section-id="${f.dataset.sectionId}" data-start="${s.start_at}" data-end="${s.end_at}">${s.start_at.slice(11,16)}–${s.end_at.slice(11,16)} · free period</button>`).join('')||'<p>No free period in this window.</p>'}</div></section>`;}).join('');}}

 }catch(err){f.querySelector('[data-personal-error]').textContent=err.message;}finally{b.disabled=false;}},true);

document.addEventListener('input',ev=>{const f=ev.target.closest('[data-form="organiser-event"]');if(!f)return;if(ev.target.name==='location'){const target=f.querySelector('[data-event-location-link]');if(target)target.innerHTML=ev.target.value.trim()?appleDestinationLink(ev.target.value.trim()):'';}if(!['date','start_time','location','journey_origin','journey_mode','departure_buffer','arrival_buffer'].includes(ev.target.name))return;if(f.personalJourneys){f.personalJourneys=null;f.querySelector('[data-journey-result]').textContent='Details changed. Search journeys again before choosing a route.';}});
document.addEventListener('change',ev=>{const select=ev.target.closest('[data-form="organiser-event"] select[name="calendar_id"]');if(select?.value==='__create__'){select.value='';void createEventCalendar(select.form).catch(error=>toast(error.message));}});

function appleDirectionsURL(home,destination,mode=''){
 const params=new URLSearchParams();
 if(String(home||'').trim())params.set('source',String(home).trim());
 params.set('destination',String(destination||'').trim());
 const mapMode={drive:'driving',walk:'walking',bus:'transit',train:'transit',transit:'transit'}[mode];
 if(mapMode)params.set('mode',mapMode);
 if(mode==='bus')params.set('transit-preferences','bus');
 if(mode==='train')params.set('transit-preferences','commuter');
 return 'https://maps.apple.com/directions?'+params.toString();
}
function appleDestinationLink(destination,mode='',label=''){
 const value=String(destination||'').trim();
 if(!value)return '';
 const text=String(label||value).trim()||value;
 const url=appleDirectionsURL('',value,mode);
 return `<a class="apple-maps-link" href="${escapeHtml(url)}" aria-label="Open route to ${escapeHtml(text)} in Apple Maps">${escapeHtml(text)}<span class="apple-maps-arrow" aria-hidden="true">↗</span></a>`;
}

function travelReminderMinutes(notes) { const m=(notes||'').match(/\[Align travel reminder: (\d{1,5}) minutes before\]/); return m && Number(m[1])>0 && Number(m[1])<=10080 ? Number(m[1]) : ''; }
function travelReminderFields(notes='') {
  const value=travelReminderMinutes(notes);
  const offsets = (typeof ALERT_OFFSETS !== 'undefined' ? ALERT_OFFSETS : [[15,'15 minutes'],[30,'30 minutes'],[45,'45 minutes'],[60,'1 hour'],[90,'90 minutes'],[120,'2 hours']]);
  const options = [...offsets];
  if (value && !options.some(([minutes]) => minutes === value)) options.push([value, `${value} minutes`]);
  options.sort((a,b)=>a[0]-b[0]);
  return `<fieldset class="travel-reminder"><legend>Travel reminder</legend><label class="field">Remind me to leave<select name="travel_reminder"><option value="">No extra travel reminder</option>${options.map(([n,label])=>`<option value="${n}" ${n===value?'selected':''}>${label} before</option>`).join('')}</select></label><p class="helper">Allow for the whole journey, including walking, connections and arriving early. This is a fixed reminder, not a live travel calculation. Your connected calendar delivers the alert; enable alerts for that calendar. Calendar notifications follow the settings in your connected calendar app. Timed events only.</p></fieldset>`;
}
function travelReminderNotes(notes,value) { const clean=(notes||'').replace(/\n?\[Align travel reminder: \d{1,5} minutes before\]/g,'').trim();const n=Number(value);if(value && (!Number.isInteger(n)||n<1||n>10080))throw new Error('Choose a valid travel reminder.');return clean+(n?`\n[Align travel reminder: ${n} minutes before]`:''); }

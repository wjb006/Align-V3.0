function travelRouteStrip(journey={}) {
  const e=escapeHtml, steps=Array.isArray(journey.steps)?journey.steps:[];
  const clock=value=>typeof journeyClock==='function'?journeyClock(value):String(value||'').slice(11,16);
  const duration=step=>{
    if(Number.isFinite(Number(step?.minutes))&&Number(step.minutes)>0)return Math.round(Number(step.minutes));
    const start=step?.expected_start||step?.start, end=step?.expected_end||step?.end;
    if(start&&end){const mins=Math.ceil((new Date(end)-new Date(start))/60000);if(Number.isFinite(mins)&&mins>0)return mins;}
    return null;
  };
  const item=(label,value,step=null)=>{
    const art=step&&typeof journeyModeArtwork==='function'?journeyModeArtwork(step,30):(typeof journeyModeArtwork==='function'?journeyModeArtwork({mode:'walk'},30):'');
    return '<span class="journey-time-icon">'+art+'<span class="journey-time-copy"><small>'+e(label)+'</small><strong>'+e(value)+'</strong></span></span>';
  };
  const entries=[];
  const leave=journey.leave_at||journey.departure||journey.depart_at;
  const arrive=journey.arrival_at||journey.arrival||journey.arrive_at;
  if(leave)entries.push(item('Leave',clock(leave)));
  for(const step of steps){
    const mode=String(step.mode||'').toLowerCase();
    const label=mode==='walk'?'Walk':mode==='bus'?'Bus':(['train','rail'].includes(mode)?'Train':mode==='drive'?'Drive':'Travel');
    const mins=duration(step);
    entries.push(item(label,mins?mins+' min':clock(step.expected_start||step.start)||'—',step));
  }
  if(arrive)entries.push(item('Arrive',clock(arrive)));
  return entries.length?'<div class="compact-event-details journey-event-details"><div class="journey-itinerary-strip">'+entries.join('<span class="shift-travel-arrow">›</span>')+'</div></div>':'';
}
function postTravelSummary(item) {
  const info=item.post_travel;if(!info?.enabled||!info?.journey)return '';
  const e=escapeHtml, journey=info.journey||null;
  const heading=info.historical?'Planned return journey':(info.deadline?'Travel to next event':'Travel home');
  const from=String(info.origin||item.location||'').trim(),to=String(info.destination_name||info.destination||'').trim();
  const routeLine=to?'<small>'+(from?e(from)+' → ':'')+e(to)+'</small>':'';
  let itinerary=travelRouteStrip(journey);
  if(!itinerary&&journey?.notes&&typeof journeyEventSummary==='function'){
    const notes='[Align travel]\\n'+journey.notes+'\\n[/Align travel]'+(journey.steps?.length?'\\n[Align travel steps]\\n'+JSON.stringify(journey.steps)+'\\n[/Align travel steps]':'');
    itinerary=journeyEventSummary(notes);
  }
  if(!itinerary&&journey?.notes)itinerary='<p class="shift-travel-refresh">'+e(journey.notes)+'</p>';
  if(!itinerary)return '';
  return '<section class="shift-travel-itinerary-wrap" aria-label="'+heading+' journey"><strong>'+heading+routeLine+'</strong>'+itinerary+'</section>';
}
function postTravelFields(info={}) {
  return `<label class="setup-check"><input type="checkbox" name="show_post_travel" ${info.enabled?'checked':''}> Show post event travel information</label><p class="helper">Travel from this event to the next event with a location starting within one hour, or home otherwise.</p><label>Travel after event<select name="post_travel_mode">${[['transit','Bus and train'],['bus','Bus'],['train','Train'],['drive','Driving']].map(([v,l])=>`<option value="${v}" ${(info.mode||personalPrefs().default_travel||'transit')===v?'selected':''}>${l}</option>`).join('')}</select></label>`;
}
async function savePostTravel(kind,id,form) {
  if(!form.elements?.show_post_travel)return;
  const result=await api('/api/personal/post-event-travel',{method:'POST',body:{kind,id:Number(id),enabled:form.elements.show_post_travel.checked,mode:form.elements.post_travel_mode.value,plan:form.elements.show_post_travel.checked}});
  return result.error;
}
async function mountPostTravelEditor(kind,id) {
  if(!id)return;
  const container=document.createElement('div');container.className='card settings-form';
  container.innerHTML='<p>Loading post event travel preference…</p>';
  const root=modalRoot.querySelector('.settings-form,.form-grid');if(!root)return;root.append(container);
  try {
    const info=await api('/api/personal/post-event-travel',{method:'POST',body:{kind,id:Number(id)}});
    if(!container.isConnected)return;
    container.innerHTML=`<div data-post-editor data-kind="${kind}" data-id="${Number(id)}">${postTravelFields(info)}<button type="button" class="secondary-button" data-save-post>Save / refresh post event travel</button><p class="helper">Save any event changes first. This preference is saved separately.</p><div data-post-result>${postTravelSummary({post_travel:info})}</div></div>`;
  } catch(error){container.textContent=error.message;}
}
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-save-post]');if(!button)return;
  event.stopPropagation();button.disabled=true;
  const root=button.closest('[data-post-editor]'),output=root.querySelector('[data-post-result]');
  try {
    const info=await api('/api/personal/post-event-travel',{method:'POST',body:{kind:root.dataset.kind,id:Number(root.dataset.id),enabled:root.querySelector('[name="show_post_travel"]').checked,mode:root.querySelector('[name="post_travel_mode"]').value,plan:root.querySelector('[name="show_post_travel"]').checked}});
    output.innerHTML=info.error?`<p role="alert">${escapeHtml(info.error)}</p>`:info.enabled?postTravelSummary({post_travel:info}):'<p>Post event travel is off.</p>';
    if(info.enabled&&!info.error)output.querySelector('details')?.setAttribute('open','');
  } catch(error){output.textContent=error.message;}finally{button.disabled=false;}
});
function parseAlignDateTime(value) {
  const text=String(value||'').trim();
  if(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(text)){
    const absolute=new Date(text);
    return Number.isFinite(absolute.getTime())?absolute:null;
  }
  const match=text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if(!match){
    const fallback=new Date(text);
    return Number.isFinite(fallback.getTime())?fallback:null;
  }
  // Align stores planner times as Europe/London wall clocks without an offset.
  const want=Date.UTC(Number(match[1]),Number(match[2])-1,Number(match[3]),Number(match[4]||0),Number(match[5]||0),Number(match[6]||0));
  let instant=want;
  const formatter=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
  for(let i=0;i<2;i+=1){
    const bag=Object.fromEntries(formatter.formatToParts(new Date(instant)).map(part=>[part.type,part.value]));
    const got=Date.UTC(Number(bag.year),Number(bag.month)-1,Number(bag.day),Number(bag.hour),Number(bag.minute),Number(bag.second));
    instant+=want-got;
  }
  return new Date(instant);
}
function upcomingNow(item) {
  let end;
  if(item.end_at)end=parseAlignDateTime(item.end_at);
  else {
    end=parseAlignDateTime(`${item.work_date}T${item.end_time}`);
    const start=parseAlignDateTime(`${item.work_date}T${item.start_time}`);
    if(end&&start&&end.getTime()<=start.getTime())end=new Date(end.getTime()+86400000);
  }
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/London', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const startDay = String(item?.start_at || item?.work_date || '').slice(0, 10);
  return !!(startDay === today || (end && end.getTime() > Date.now()));
}
function eventStartAt(item) {
  if(item?.start_at)return parseAlignDateTime(item.start_at);
  if(item?.work_date&&item?.start_time)return parseAlignDateTime(`${item.work_date}T${item.start_time}`);
  return null;
}
function eventEndAt(item) {
  if(item?.end_at)return parseAlignDateTime(item.end_at);
  if(item?.work_date&&item?.end_time){
    const end=parseAlignDateTime(`${item.work_date}T${item.end_time}`);
    const start=eventStartAt(item);
    if(end&&start&&end.getTime()<=start.getTime())return new Date(end.getTime()+86400000);
    return end;
  }
  return null;
}
function eventIsUnderway(item) {
  const start=eventStartAt(item),end=eventEndAt(item),now=Date.now();
  return !!(start&&end&&Number.isFinite(start.getTime())&&Number.isFinite(end.getTime())&&start.getTime()<=now&&end.getTime()>now);
}
function eventHasFinished(item) {
  const end=eventEndAt(item);
  return !!(end&&Number.isFinite(end.getTime())&&end.getTime()<=Date.now());
}
function eventTravelMarkup(item,{includeInbound=true}={}) {
  if(!item||eventIsUnderway(item))return '';
  const post=postTravelSummary(item);
  if(eventHasFinished(item))return post;
  if(!includeInbound)return post;
  const notes=item.notes||'';
  const travel=typeof journeyEventSummary==='function'?journeyEventSummary(notes):(typeof travelCard==='function'?travelCard(notes):(typeof savedTravelSummary==='function'?savedTravelSummary(notes):''));
  return travel+post;
}
setInterval(()=>{
  if(state.boot&&['home','today'].includes(state.tab)&&!modalRoot.textContent.trim())render();
},60000);

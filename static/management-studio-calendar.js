(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pad = n => String(n).padStart(2, '0');
  const dateKey = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const parse = value => { const d = new Date(value); return Number.isNaN(d.getTime()) ? null : d; };
  const startOfWeek = d => { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); x.setDate(x.getDate() - ((x.getDay()+6)%7)); return x; };
  const fmt = d => d.toLocaleDateString(undefined,{weekday:'short',day:'numeric',month:'short'});
  const time = d => d.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'});
  let mounted = false, mode = 'month', cursor = new Date(), sections = [], events = [], busy = false;
  const api = async (url, options={}) => {
    const r = await fetch(url,{cache:'no-store',credentials:'same-origin',headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
    const body = await r.json().catch(()=>({}));
    if (!r.ok) throw new Error(body.message || body.error || 'Align could not load the calendar. Please retry.');
    return body;
  };
  function range() {
    const base = new Date(cursor.getFullYear(),cursor.getMonth(),cursor.getDate());
    if(mode==='month') return [new Date(base.getFullYear(),base.getMonth(),1),new Date(base.getFullYear(),base.getMonth()+1,1)];
    if(mode==='week') { const s=startOfWeek(base); const e=new Date(s);e.setDate(e.getDate()+7);return [s,e]; }
    const s=base,e=new Date(s);e.setDate(e.getDate()+1);return [s,e];
  }
  function visibleEvents() {
    const [start,end]=range();
    return events.filter(e=>e.start && e.end && e.start<end && e.end>start).sort((a,b)=>a.start-b.start);
  }
  function eventCard(e) {
    const stamp = e.allDay ? 'All day' : time(e.start);
    return `<button class="sc-event" type="button" data-event-id="${esc(e.id)}" aria-label="${esc(e.title)}, ${esc(stamp)}"><time>${esc(stamp)}</time><strong>${esc(e.title)}</strong><small>${esc(e.sectionName || e.source_name || 'Align event')}${e.location ? ' · '+esc(e.location):''}</small></button>`;
  }
  function render() {
    const root=document.getElementById('studio-calendar');
    if(!root)return;
    const [from,to]=range(), list=visibleEvents();
    const heading=mode==='month'?cursor.toLocaleDateString(undefined,{month:'long',year:'numeric'}):mode==='week'?`${fmt(from)} – ${fmt(new Date(to.getTime()-86400000))}`:fmt(from);
    let body='';
    if(mode==='month') {
      const first=new Date(cursor.getFullYear(),cursor.getMonth(),1), gridStart=startOfWeek(first);
      const days=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
      body='<div class="sc-month-grid">'+days.map(x=>`<div class="sc-weekday">${x}</div>`).join('');
      for(let i=0;i<42;i++){const d=new Date(gridStart);d.setDate(d.getDate()+i);const todays=list.filter(e=>dateKey(e.start)===dateKey(d));body+=`<div class="sc-month-day ${d.getMonth()!==cursor.getMonth()?'is-outside':''} ${dateKey(d)===dateKey(new Date())?'is-today':''}"><span class="sc-date">${d.getDate()}</span>${todays.slice(0,3).map(eventCard).join('')}${todays.length>3?'<small>+'+(todays.length-3)+' more</small>':''}</div>`;}
      body+='</div>';
    } else if(mode==='week') {
      body='<div class="sc-week-grid">'+Array.from({length:7},(_,i)=>{const d=new Date(from);d.setDate(d.getDate()+i);const day=list.filter(e=>dateKey(e.start)===dateKey(d));return `<section class="sc-week-day"><h3>${esc(fmt(d))}</h3>${day.map(eventCard).join('')||'<p class="sc-empty-day">No events</p>'}</section>`;}).join('')+'</div>';
    } else {
      const day=list.filter(e=>dateKey(e.start)===dateKey(from));
      if(mode==='day') body=`<div class="sc-day-list">${day.map(eventCard).join('')||'<p class="sc-empty-day">No events scheduled for this day.</p>'}</div>`;
      else {
        const nowHour=new Date().getHours();
        body='<div class="sc-time-grid">'+Array.from({length:24},(_,hour)=>{const matches=day.filter(e=>!e.allDay && e.start.getHours()===hour);return `<div class="sc-hour" data-hour="${hour}"${hour===nowHour?' aria-current="time"':''}><time>${pad(hour)}:00</time><div>${matches.map(eventCard).join('')}</div></div>`;}).join('')+'</div>';
        const allDay=day.filter(e=>e.allDay);if(allDay.length)body='<div class="sc-all-day"><strong>All day</strong>'+allDay.map(eventCard).join('')+'</div>'+body;
      }
    }
    root.innerHTML=`<div class="sc-toolbar"><div class="sc-nav"><button type="button" data-cal-nav="-1" aria-label="Previous ${mode}">‹</button><button type="button" data-cal-today>Today</button><button type="button" data-cal-nav="1" aria-label="Next ${mode}">›</button><h2>${esc(heading)}</h2></div><div class="sc-modes" role="group" aria-label="Calendar view">${[['month','Month'],['week','Week'],['day','Day'],['hour','Day / Hour']].map(([key,label])=>`<button type="button" data-cal-mode="${key}" aria-pressed="${mode===key}">${label}</button>`).join('')}<button type="button" data-cal-add>+ Add event</button></div></div><p class="sc-source"><span></span> Source: saved Align events on this server. Imported calendar events are shown read-only.</p><div class="sc-status" role="status" aria-live="polite">${busy?'Loading saved events…':events.length?events.length+' saved events loaded.':'No saved events found in the selected date range.'}</div>${body}<form class="sc-add-form" hidden><h3>Add an Align event</h3><label>Title<input name="title" required maxlength="160"></label><div class="sc-form-grid"><label>Section<select name="section_id" required></select></label><label>Date<input name="date" type="date" required value="${dateKey(cursor)}"></label><label>Start<input name="start" type="time" value="09:00" required></label><label>End<input name="end" type="time" value="10:00" required></label></div><label>Location (optional)<input name="location" maxlength="240"></label><label>Notes (optional)<textarea name="notes" rows="2" maxlength="4000"></textarea></label><label class="sc-check"><input type="checkbox" name="all_day"> All-day event</label><div class="sc-form-actions"><button type="button" data-cal-cancel>Cancel</button><button type="submit">Save event</button></div></form>`;
    const select=root.querySelector('[name="section_id"]');if(select)select.innerHTML=sections.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');
    if(mode==='hour') root.querySelector(`[data-hour="${new Date().getHours()}"]`)?.scrollIntoView({block:'center'});
  }
  async function load() {
    busy=true;render();
    try {
      sections=await api('/api/sections');
      const results=await Promise.all(sections.map(s=>api('/api/sections/'+encodeURIComponent(s.id)).then(detail=>(detail.events||[]).map(e=>({...e,sectionName:s.name}))).catch(()=>[])));
      const map=new Map();results.flat().forEach(e=>{const start=parse(e.start_at),end=parse(e.end_at);if(!start||!end)return;const key=String(e.source_kind||'align')+':'+String(e.id)+':'+start.toISOString();map.set(key,{...e,start,end,allDay:Boolean(e.all_day)});});
      events=[...map.values()];busy=false;render();
      const status=document.querySelector('#studio-calendar .sc-status');if(status)status.textContent=events.length?`Loaded ${events.length} saved Align event(s). Times use this device's local timezone.`:'No saved events were returned by Align for these sections.';
    } catch(error) {
      busy=false;const root=document.getElementById('studio-calendar');if(root)root.innerHTML=`<div class="sc-error" role="alert"><strong>Calendar could not be loaded</strong><p>${esc(error.message)}</p><button type="button" data-cal-retry>Retry</button></div>`;
    }
  }
  function navigate(delta){if(mode==='month')cursor=new Date(cursor.getFullYear(),cursor.getMonth()+delta,1);else if(mode==='week')cursor.setDate(cursor.getDate()+delta*7);else cursor.setDate(cursor.getDate()+delta);render();}
  function mount(host){if(!host)return;host.innerHTML='<div id="studio-calendar" class="studio-working-calendar"><p>Loading saved Align events…</p></div>';mounted=true;load();}
  document.addEventListener('click',e=>{
    const root=document.getElementById('studio-calendar');if(!root||!root.contains(e.target))return;
    const modeBtn=e.target.closest('[data-cal-mode]');if(modeBtn){mode=modeBtn.dataset.calMode;render();return;}
    if(e.target.closest('[data-cal-nav]')){navigate(Number(e.target.closest('[data-cal-nav]').dataset.calNav));return;}
    if(e.target.closest('[data-cal-today]')){cursor=new Date();render();return;}
    if(e.target.closest('[data-cal-add]')){const form=root.querySelector('.sc-add-form');form.hidden=!form.hidden;return;}
    if(e.target.closest('[data-cal-cancel]')){root.querySelector('.sc-add-form').hidden=true;return;}
    if(e.target.closest('[data-cal-retry]')){load();}
  });
  document.addEventListener('change',e=>{if(e.target.matches('.sc-add-form [name="all_day"]')){const form=e.target.closest('form');form.querySelector('[name="start"]').disabled=e.target.checked;form.querySelector('[name="end"]').disabled=e.target.checked;}});
  document.addEventListener('submit',async e=>{
    const form=e.target.closest('.sc-add-form');if(!form)return;e.preventDefault();
    const data=new FormData(form), section=String(data.get('section_id')||'');if(!section){alert('Create or activate a section in Align before adding events.');return;}
    const date=String(data.get('date')),allDay=data.get('all_day')==='on';
    const payload={title:String(data.get('title')),all_day:allDay,date,start_at:date+'T'+String(data.get('start')),end_at:date+'T'+String(data.get('end')),location:String(data.get('location')||''),notes:String(data.get('notes')||'')};
    const save=form.querySelector('[type="submit"]');save.disabled=true;save.textContent='Saving…';
    try{await api('/api/sections/'+encodeURIComponent(section)+'/events',{method:'POST',body:JSON.stringify(payload)});cursor=new Date(date+'T12:00:00');form.reset();form.hidden=true;await load();window.AlignStudioNotice?.('Event saved to Align.','saved');}
    catch(error){window.AlignStudioNotice?.(error.message,'error');}
    finally{save.disabled=false;save.textContent='Save event';}
  });
  window.AlignStudioCalendar={mount};
})();
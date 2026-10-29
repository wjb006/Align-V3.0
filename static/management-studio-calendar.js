(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pad = n => String(n).padStart(2, '0');
  const dateKey = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const parse = value => { const d = new Date(value); return Number.isNaN(d.getTime()) ? null : d; };
  const startOfWeek = d => { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); x.setDate(x.getDate() - ((x.getDay()+6)%7)); return x; };
  const dayStart = d => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const nextDay = d => { const x = dayStart(d); x.setDate(x.getDate()+1); return x; };
  const overlaps = (e, start, end) => e.start < end && e.end > start;
  const fmt = d => d.toLocaleDateString(undefined,{weekday:'short',day:'numeric',month:'short'});
  const time = d => d.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'});
  const keyOf = e => `${e.source_kind || 'align'}:${e.id}`;
  let mode = 'month', cursor = new Date(), sections = [], events = [], busy = false, selected = '', editing = null;
  const byKey = new Map();
  const api = async (url, options={}) => {
    const r = await fetch(url,{cache:'no-store',credentials:'same-origin',headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
    const body = await r.json().catch(()=>({}));
    if (!r.ok) throw new Error(body.message || body.error || 'Align could not load the calendar. Please retry.');
    return body;
  };
  function range() {
    const base = new Date(cursor.getFullYear(),cursor.getMonth(),cursor.getDate());
    if(mode==='month') return [new Date(base.getFullYear(),base.getMonth(),1),new Date(base.getFullYear(),base.getMonth()+1,1)];
    if(mode==='week') { const s=startOfWeek(base); return [s, nextDay(new Date(s.getFullYear(), s.getMonth(), s.getDate()+6))]; }
    return [dayStart(base), nextDay(base)];
  }
  function visibleEvents() {
    const [start,end]=range();
    return events.filter(e=>e.start && e.end && overlaps(e,start,end)).sort((a,b)=>a.start-b.start);
  }
  function eventCard(e) {
    const stamp = e.allDay ? 'All day' : `${time(e.start)}–${time(e.end)}`;
    return `<button class="sc-event" type="button" data-event-key="${esc(keyOf(e))}" aria-label="${esc(e.title)}, ${esc(stamp)}"><time>${esc(stamp)}</time><strong>${esc(e.title)}</strong><small>${esc(e.sectionName || e.source_name || 'Align event')}${e.location ? ' · '+esc(e.location):''}</small></button>`;
  }
  function hourGrid(day, list) {
    const start = dayStart(day), end = nextDay(day);
    const timed = list.filter(e => !e.allDay && overlaps(e, start, end)).sort((a,b)=>a.start-b.start || a.end-b.end);
    const placed = [];
    timed.forEach(event => {
      let col = 0;
      while (placed.some(item => item.col === col && overlaps(item.event, event.start, event.end))) col += 1;
      placed.push({event, col});
    });
    const columns = Math.max(1, ...placed.map(item => item.col + 1));
    const px = 52;
    const hours = Array.from({length:24}, (_, hour) => `<div class="sc-hour"><time>${pad(hour)}:00</time><div></div></div>`).join('');
    const blocks = placed.map(({event, col}) => {
      const startMin = Math.max(0, (event.start - start) / 60000);
      const endMin = Math.min(1440, (event.end - start) / 60000);
      const top = (startMin / 60) * px;
      const height = Math.max(28, ((Math.max(endMin, startMin + 20) - startMin) / 60) * px);
      const left = `calc(78px + (100% - 86px) * ${col} / ${columns})`;
      const width = `calc((100% - 86px) / ${columns} - 6px)`;
      return `<button class="sc-event sc-span" type="button" data-event-key="${esc(keyOf(event))}" style="top:${top}px;height:${height}px;left:${left};width:${width}" aria-label="${esc(event.title)}, ${esc(time(event.start))} to ${esc(time(event.end))}"><time>${esc(time(event.start))}–${esc(time(event.end))}</time><strong>${esc(event.title)}</strong></button>`;
    }).join('');
    const allDay = list.filter(e => e.allDay && overlaps(e, start, end));
    const banner = allDay.length ? `<div class="sc-all-day"><strong>All day</strong>${allDay.map(eventCard).join('')}</div>` : '';
    return `${banner}<div class="sc-time-wrap"><div class="sc-time-hours">${hours}${blocks}</div></div>`;
  }
  function detail() {
    const event = byKey.get(selected);
    if (!event) return '';
    const when = event.allDay ? `All day · ${fmt(event.start)}` : `${fmt(event.start)} · ${time(event.start)}–${time(event.end)}`;
    const imported = event.source_kind && event.source_kind !== 'align';
    return `<section class="sc-detail"><h3>${esc(event.title)}</h3><p>${esc(when)}</p><p>${esc(event.sectionName || event.source_name || 'Align event')}</p><p>${esc(event.location || 'No location')}</p>${event.notes ? `<p>${esc(event.notes)}</p>` : ''}<p class="sc-source"><span></span>${imported ? 'Imported calendar event, shown read-only.' : 'Saved Align event on this computer. Times use this computer’s local timezone.'}</p><div class="sc-form-actions">${imported ? '' : '<button type="button" data-cal-edit>Edit event</button>'}<button type="button" data-cal-close>Close</button></div></section>`;
  }
  function formValues(event) {
    const when = event ? event.start : cursor;
    const end = event ? event.end : null;
    return {
      title: event ? event.title : '',
      section: event ? String(event.section_id || '') : (sections[0] ? String(sections[0].id) : ''),
      date: dateKey(when),
      start: event && !event.allDay ? `${pad(event.start.getHours())}:${pad(event.start.getMinutes())}` : '09:00',
      end: end && event && !event.allDay ? `${pad(end.getHours())}:${pad(end.getMinutes())}` : '10:00',
      location: event ? (event.location || '') : '',
      notes: event ? (event.notes || '') : '',
      allDay: Boolean(event && event.allDay)
    };
  }
  function render() {
    const root=document.getElementById('studio-calendar');
    if(!root)return;
    const [from,to]=range(), list=visibleEvents();
    const heading=mode==='month'?cursor.toLocaleDateString(undefined,{month:'long',year:'numeric'}):mode==='week'?`${fmt(from)} – ${fmt(new Date(to.getTime()-86400000))}`:fmt(from);
    let body='';
    if(mode==='month') {
      const gridStart=startOfWeek(new Date(cursor.getFullYear(),cursor.getMonth(),1));
      body='<div class="sc-month-grid">'+['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(x=>`<div class="sc-weekday">${x}</div>`).join('');
      for(let i=0;i<42;i++){
        const d=new Date(gridStart); d.setDate(d.getDate()+i);
        const todays=list.filter(e=>overlaps(e, dayStart(d), nextDay(d)));
        body+=`<div class="sc-month-day ${d.getMonth()!==cursor.getMonth()?'is-outside':''} ${dateKey(d)===dateKey(new Date())?'is-today':''}"><span class="sc-date">${d.getDate()}</span>${todays.slice(0,3).map(eventCard).join('')}${todays.length>3?'<small>+'+(todays.length-3)+' more</small>':''}</div>`;
      }
      body+='</div>';
    } else if(mode==='week') {
      body='<div class="sc-week-grid">'+Array.from({length:7},(_,i)=>{
        const d=new Date(from); d.setDate(d.getDate()+i);
        const day=list.filter(e=>overlaps(e, dayStart(d), nextDay(d)));
        return `<section class="sc-week-day"><h3>${esc(fmt(d))}</h3>${day.map(eventCard).join('')||'<p class="sc-empty-day">No events</p>'}</section>`;
      }).join('')+'</div>';
    } else if(mode==='day') {
      const day=list.filter(e=>overlaps(e, from, to));
      body=`<div class="sc-day-list">${day.map(eventCard).join('')||'<p class="sc-empty-day">No events scheduled for this day.</p>'}</div>`;
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
      body = list.length || true ? hourGrid(from, list) : '';
    }
    const values = formValues(editing);
    const status = busy ? 'Loading saved events…' : (events.length ? `${events.length} saved events loaded. Times use this computer’s local timezone.` : 'No saved events found.');
    root.innerHTML=`<div class="sc-toolbar"><div class="sc-nav"><button type="button" data-cal-nav="-1" aria-label="Previous ${mode}">‹</button><button type="button" data-cal-today>Today</button><button type="button" data-cal-nav="1" aria-label="Next ${mode}">›</button><h2>${esc(heading)}</h2></div><div class="sc-modes" role="group" aria-label="Calendar view">${[['month','Month'],['week','Week'],['day','Day'],['hour','Day / Hour']].map(([key,label])=>`<button type="button" data-cal-mode="${key}" aria-pressed="${mode===key}">${label}</button>`).join('')}<button type="button" data-cal-add>+ Add event</button></div></div><p class="sc-source"><span></span> Source: saved Align events on this server. Imported calendar events are shown read-only.</p><div class="sc-status" role="status" aria-live="polite">${esc(status)}</div>${detail()}${body}<form class="sc-add-form" ${editing || root.dataset.adding==='1' ? '' : 'hidden'}><h3>${editing ? 'Edit Align event' : 'Add an Align event'}</h3><label>Title<input name="title" required maxlength="160" value="${esc(values.title)}"></label><div class="sc-form-grid"><label>Section<select name="section_id" required>${sections.map(s=>`<option value="${s.id}"${String(s.id)===values.section?' selected':''}>${esc(s.name)}</option>`).join('')}</select></label><label>Date<input name="date" type="date" required value="${esc(values.date)}"></label><label>Start<input name="start" type="time" value="${esc(values.start)}" required ${values.allDay?'disabled':''}></label><label>End<input name="end" type="time" value="${esc(values.end)}" required ${values.allDay?'disabled':''}></label></div><label>Location (optional)<input name="location" maxlength="240" value="${esc(values.location)}"></label><label>Notes (optional)<textarea name="notes" rows="2" maxlength="4000">${esc(values.notes)}</textarea></label><label class="sc-check"><input type="checkbox" name="all_day" ${values.allDay?'checked':''}> All-day event</label><div class="sc-form-actions"><button type="button" data-cal-cancel>Cancel</button><button type="submit">${editing ? 'Save changes' : 'Save event'}</button></div></form>`;
  }
  async function load() {
    busy=true; render();
    try {
      sections=await api('/api/sections');
      const results=await Promise.all(sections.map(s=>api('/api/sections/'+encodeURIComponent(s.id)).then(detailBody=>(detailBody.events||[]).map(e=>({...e,sectionName:s.name}))).catch(()=>[])));
      byKey.clear();
      results.flat().forEach(e=>{
        const start=parse(e.start_at), end=parse(e.end_at);
        if(!start||!end)return;
        const event={...e,start,end,allDay:Boolean(e.all_day)};
        byKey.set(keyOf(event), event);
      });
      events=[...byKey.values()];
      if (selected && !byKey.has(selected)) selected = '';
      busy=false; render();
    } catch(error) {
      busy=false;
      const root=document.getElementById('studio-calendar');
      if(root) root.innerHTML=`<div class="sc-error" role="alert"><strong>Calendar could not be loaded</strong><p>${esc(error.message)}</p><button type="button" data-cal-retry>Retry</button></div>`;
    }
  }
  function navigate(delta){
    if(mode==='month') cursor=new Date(cursor.getFullYear(),cursor.getMonth()+delta,1);
    else if(mode==='week') cursor.setDate(cursor.getDate()+delta*7);
    else cursor.setDate(cursor.getDate()+delta);
    render();
  }
  function mount(host){if(!host)return; host.innerHTML='<div id="studio-calendar" class="studio-working-calendar"><p>Loading saved Align events…</p></div>'; load();}
  document.addEventListener('click',e=>{
    const root=document.getElementById('studio-calendar');
    if(!root||!root.contains(e.target))return;
    const eventButton=e.target.closest('[data-event-key]');
    if(eventButton){selected=eventButton.dataset.eventKey; editing=null; root.dataset.adding=''; render(); return;}
    const modeBtn=e.target.closest('[data-cal-mode]');
    if(modeBtn){mode=modeBtn.dataset.calMode; render(); return;}
    if(e.target.closest('[data-cal-nav]')){navigate(Number(e.target.closest('[data-cal-nav]').dataset.calNav)); return;}
    if(e.target.closest('[data-cal-today]')){cursor=new Date(); render(); return;}
    if(e.target.closest('[data-cal-add]')){editing=null; selected=''; root.dataset.adding = root.dataset.adding==='1' ? '' : '1'; render(); return;}
    if(e.target.closest('[data-cal-edit]')){editing=byKey.get(selected)||null; root.dataset.adding=''; render(); return;}
    if(e.target.closest('[data-cal-close]')){selected=''; render(); return;}
    if(e.target.closest('[data-cal-cancel]')){editing=null; root.dataset.adding=''; render(); return;}
    if(e.target.closest('[data-cal-retry]')){load();}
  });
  document.addEventListener('change',e=>{
    if(!e.target.matches('.sc-add-form [name="all_day"]')) return;
    const form=e.target.closest('form');
    form.querySelector('[name="start"]').disabled=e.target.checked;
    form.querySelector('[name="end"]').disabled=e.target.checked;
  });
  document.addEventListener('submit',async e=>{
    const form=e.target.closest('.sc-add-form');
    if(!form)return;
    e.preventDefault();
    const data=new FormData(form);
    const section=String(data.get('section_id')||'');
    if(!section){window.AlignStudioNotice?.('Create or activate a section in Align before adding events.','error'); return;}
    const date=String(data.get('date'));
    const allDay=data.get('all_day')==='on';
    const payload={title:String(data.get('title')||''), all_day:allDay, date, start_at:date+'T'+String(data.get('start')||'00:00'), end_at:date+'T'+String(data.get('end')||'00:00'), location:String(data.get('location')||''), notes:String(data.get('notes')||'')};
    const save=form.querySelector('[type="submit"]');
    save.disabled=true; save.textContent='Saving…';
    try{
      if(editing && editing.source_kind!=='icloud') await api('/api/organiser-events/'+encodeURIComponent(editing.id),{method:'PUT',body:JSON.stringify(payload)});
      else await api('/api/sections/'+encodeURIComponent(section)+'/events',{method:'POST',body:JSON.stringify(payload)});
      cursor=new Date(date+'T12:00:00');
      editing=null; selected='';
      const root=document.getElementById('studio-calendar');
      if(root) root.dataset.adding='';
      await load();
      window.AlignStudioNotice?.('Event saved to Align.','saved');
    } catch(error) {
      window.AlignStudioNotice?.(error.message,'error');
      save.disabled=false; save.textContent=editing ? 'Save changes' : 'Save event';
    }
  });
  window.AlignStudioCalendar={mount};
})();

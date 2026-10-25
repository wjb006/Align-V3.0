/* Restored beta shift planner for Align V3. */
(function () {
  const getToday = () => {
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
  };
  const shiftDay = (iso, amount) => {
    const d = new Date(iso + 'T12:00:00');
    d.setDate(d.getDate()+amount);
    return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
  };
  const monday = iso => {
    const d = new Date(iso+'T12:00:00');
    d.setDate(d.getDate()-((d.getDay()+6)%7));
    return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
  };
  const esc = value => typeof escapeHtml === 'function' ? escapeHtml(value == null ? '' : String(value)) : String(value ?? '').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const fmtDay = iso => new Date(iso+'T12:00:00').toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'short'});
  const fmtMonth = iso => new Date(iso+'T12:00:00').toLocaleDateString('en-GB',{month:'long',year:'numeric'});
  const fmtHours = n => Number(n||0).toLocaleString('en-GB',{maximumFractionDigits:2})+'h';
  function init() {
    if (!state.plannerMode) state.plannerMode='week';
    if (!state.plannerAnchor) state.plannerAnchor=monday(getToday());
    if (!state.shiftPlannerData) state.shiftPlannerData=null;
    if (!state.shiftPlannerLoading) state.shiftPlannerLoading=false;
    if (!state.shiftPlannerError) state.shiftPlannerError='';
    if (!state.shiftPlannerModal) state.shiftPlannerModal='';
  }
  async function load() {
    init();
    if (state.shiftPlannerLoading) return;
    state.shiftPlannerLoading=true; state.shiftPlannerError='';
    try {
      const path=state.plannerMode==='month'
        ? '/api/month?month='+encodeURIComponent(state.plannerAnchor.slice(0,7))
        : '/api/week?start='+encodeURIComponent(state.plannerAnchor);
      state.shiftPlannerData=await api(path);
    } catch(e) {
      state.shiftPlannerError=e.message||'Could not load your shift planner.';
    } finally {
      state.shiftPlannerLoading=false;
      render();
    }
  }
  function selectedShifts() {
    const data=state.shiftPlannerData||{};
    return (data.shifts||[]).slice().sort((a,b)=>(a.work_date+a.start_time).localeCompare(b.work_date+b.start_time));
  }
  function totals(shifts) {
    const counted=shifts.filter(s=>!String(s.notes||'').includes('[Align cover: given'));
    const hours=counted.reduce((n,s)=>n+Number(s.hours||0),0);
    const settings=state.boot?.settings||{};
    const contracted=Number(settings.contracted_hours||0), rate=Number(settings.rate_of_pay||0);
    const overtime=contracted>0?Math.max(0,hours-contracted):0;
    return {hours,contracted,overtime,pay:rate>0?hours*rate:0};
  }
  function shiftCard(s) {
    return '<article class="card restored-shift-card" style="--shift-colour:'+esc(s.colour||'#365CE6')+'">'+
      '<div class="restored-shift-top"><div><span class="restored-shift-date">'+esc(fmtDay(s.work_date))+'</span><h3>'+esc(s.location_name||'Shift')+'</h3><p>'+esc(s.shift_type_name||'Work')+(s.notes? ' · '+esc(s.notes):'')+'</p></div>'+
      '<span class="restored-shift-hours">'+esc(fmtHours(s.hours))+'</span></div>'+
      '<p class="restored-shift-time">'+esc(s.start_time)+'–'+esc(s.end_time)+(Number(s.break_minutes)?' · '+esc(s.break_minutes)+' min break':'')+'</p>'+
      '<div class="button-row"><button class="secondary-button" data-shift-action="edit" data-id="'+esc(s.id)+'">Edit shift</button><button class="secondary-button" data-shift-action="delete" data-id="'+esc(s.id)+'">Delete</button></div></article>';
  }
  function leaveCard(l) {
    return '<article class="card restored-leave-card"><div><strong>Annual leave</strong><p>'+esc(fmtDay(l.leave_date))+(l.notes?' · '+esc(l.notes):'')+'</p></div><button class="secondary-button" data-shift-action="delete-leave" data-id="'+esc(l.id)+'">Remove</button></article>';
  }
  function formMarkup(edit={}) {
    const data=state.shiftPlannerData||{};
    const templates=data.templates||[], locations=data.locations||[], types=data.shift_types||[];
    const template=templates.find(t=>String(t.id)===String(edit.template_id||''))||null;
    const chosenLocation=edit.location_id||template?.location_id||'';
    const chosenType=edit.shift_type_id||template?.shift_type_id||'';
    return '<section class="card restored-planner-form" id="shift-planner-form"><div class="section-head"><div><p class="eyebrow">'+(edit.id?'Edit shift':'Plan a shift')+'</p><h2>'+(edit.id?'Update shift':'Add shift')+'</h2></div><button class="secondary-button" data-shift-action="close-form">Close</button></div>'+
      '<form data-shift-form="shift" data-id="'+esc(edit.id||'')+'">'+
      '<label class="field">Saved shift pattern<select name="template_id"><option value="">Choose pattern or enter details</option>'+templates.map(t=>'<option value="'+esc(t.id)+'" '+(String(edit.template_id||'')===String(t.id)?'selected':'')+'>'+esc(t.location_name+' · '+t.label+' ('+t.start_time+'–'+t.end_time+')')+'</option>').join('')+'</select></label>'+
      '<div class="form-grid"><label class="field">Work date<input type="date" name="work_date" required value="'+esc(edit.work_date||state.plannerAnchor||getToday())+'"></label>'+
      '<label class="field">Location<select name="location_id" required><option value="">Choose location</option>'+locations.map(l=>'<option value="'+esc(l.id)+'" '+(String(chosenLocation)===String(l.id)?'selected':'')+'>'+esc(l.name)+'</option>').join('')+'</select></label>'+
      '<label class="field">Shift type<select name="shift_type_id" required><option value="">Choose shift type</option>'+types.map(t=>'<option value="'+esc(t.id)+'" '+(String(chosenType)===String(t.id)?'selected':'')+'>'+esc(t.name)+'</option>').join('')+'</select></label>'+
      '<label class="field">Start time<input type="time" name="start_time" required value="'+esc(edit.start_time||template?.start_time||'09:00')+'"></label>'+
      '<label class="field">End time<input type="time" name="end_time" required value="'+esc(edit.end_time||template?.end_time||'13:00')+'"></label>'+
      '<label class="field">Break (minutes)<input type="number" name="break_minutes" min="0" max="720" value="'+esc(edit.break_minutes??template?.break_minutes??0)+'"></label></div>'+
      '<label class="field">Notes<textarea name="notes" rows="2">'+esc(edit.notes||'')+'</textarea></label>'+
      '<div class="button-row"><button class="primary-button" type="submit">'+(edit.id?'Save changes':'Save shift')+'</button></div></form></section>';
  }
  function leaveForm() {
    return '<section class="card restored-planner-form"><div class="section-head"><div><p class="eyebrow">Time off</p><h2>Book annual leave</h2></div><button class="secondary-button" data-shift-action="close-form">Close</button></div>'+
      '<form data-shift-form="leave"><div class="form-grid"><label class="field">First day<input name="start_date" type="date" required value="'+esc(state.plannerAnchor||getToday())+'"></label><label class="field">Last day<input name="end_date" type="date" required value="'+esc(state.plannerAnchor||getToday())+'"></label></div><label class="field">Notes<textarea name="notes" rows="2"></textarea></label><button class="primary-button" type="submit">Book leave</button></form></section>';
  }
  function patternManager() {
    const d=state.shiftPlannerData||{};
    return '<section class="card restored-planner-form"><div class="section-head"><div><p class="eyebrow">Setup</p><h2>Locations, shift types and saved patterns</h2></div><button class="secondary-button" data-shift-action="close-form">Close</button></div>'+
      '<form data-shift-form="location"><h3>Add work location</h3><label class="field">Name<input name="name" required></label><label class="field">Address (optional)<input name="address"></label><button class="secondary-button" type="submit">Add location</button></form><hr>'+
      '<form data-shift-form="type"><h3>Add shift type</h3><label class="field">Name<input name="name" required placeholder="e.g. Wards, Clinic"></label><button class="secondary-button" type="submit">Add shift type</button></form><hr>'+
      '<form data-shift-form="template"><h3>Save shift pattern</h3><label class="field">Pattern name<input name="label" required placeholder="e.g. AM clinic"></label><div class="form-grid"><label class="field">Location<select name="location_id" required><option value="">Choose location</option>'+(d.locations||[]).map(l=>'<option value="'+esc(l.id)+'">'+esc(l.name)+'</option>').join('')+'</select></label><label class="field">Shift type<select name="shift_type_id" required><option value="">Choose type</option>'+(d.shift_types||[]).map(t=>'<option value="'+esc(t.id)+'">'+esc(t.name)+'</option>').join('')+'</select></label><label class="field">Start<input type="time" name="start_time" value="09:00" required></label><label class="field">End<input type="time" name="end_time" value="13:00" required></label><label class="field">Break (minutes)<input type="number" name="break_minutes" min="0" value="0"></label></div><button class="primary-button" type="submit">Save pattern</button></form></section>';
  }
  function calendarMarkup(data) {
    const month=state.plannerAnchor.slice(0,7), first=new Date(month+'-01T12:00:00');
    const count=new Date(first.getFullYear(),first.getMonth()+1,0).getDate(), offset=(first.getDay()+6)%7;
    const shifts=data.shifts||[], leaves=data.annual_leave||[];
    let cells=Array.from({length:offset},()=>'<span class="restored-month-empty"></span>').join('');
    for(let i=1;i<=count;i++){
      const day=month+'-'+String(i).padStart(2,'0'), n=shifts.filter(s=>s.work_date===day).length, leave=leaves.some(l=>l.leave_date===day);
      cells+='<button class="restored-month-day '+(day===getToday()?'is-today ':'')+(n?'has-shifts ':'')+(leave?'has-leave':'')+'" data-shift-date="'+day+'"><span>'+i+'</span>'+(n?'<small>'+n+' shift'+(n===1?'':'s')+'</small>':leave?'<small>Leave</small>':'')+'</button>';
    }
    return '<div class="restored-month-grid">'+['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d=>'<span class="restored-month-heading">'+d+'</span>').join('')+cells+'</div>';
  }
  function render() {
    init();
    if (!state.shiftPlannerData && !state.shiftPlannerLoading && !state.shiftPlannerError) { void load(); }
    const d=state.shiftPlannerData||{shifts:[],annual_leave:[],templates:[],locations:[],shift_types:[]};
    const shifts=selectedShifts(), leaves=(d.annual_leave||[]).slice().sort((a,b)=>a.leave_date.localeCompare(b.leave_date));
    const t=totals(shifts);
    const title=state.plannerMode==='month'?fmtMonth(state.plannerAnchor):'Week commencing '+fmtDay(monday(state.plannerAnchor));
    const list=state.plannerMode==='week'
      ? Array.from({length:7},(_,i)=>shiftDay(monday(state.plannerAnchor),i)).map(day=>{
        const ds=shifts.filter(s=>s.work_date===day), ls=leaves.filter(l=>l.leave_date===day);
        return '<section class="restored-planner-day"><h3>'+esc(fmtDay(day))+'</h3>'+(ds.length?ds.map(shiftCard).join(''):'')+ls.map(leaveCard).join('')+(!ds.length&&!ls.length?'<p class="restored-rest-day">Nothing planned</p>':'')+'</section>';
      }).join('')
      : calendarMarkup(d)+'<div class="restored-planner-list">'+shifts.map(shiftCard).join('')+leaves.map(leaveCard).join('')+(!shifts.length&&!leaves.length?'<p class="empty">No shifts or leave this month.</p>':'')+'</div>';
    return '<section class="page planner-page restored-planner-page"><div class="add-head"><p class="eyebrow">Work schedule</p><h1>Planner</h1><p class="subtle">Your shifts, saved patterns and annual leave — together in one place.</p></div>'+
      '<div class="card restored-planner-toolbar"><div class="schedule-week-nav"><button class="secondary-button" data-shift-action="previous" aria-label="Previous '+state.plannerMode+'">‹</button><h2>'+esc(title)+'</h2><button class="secondary-button" data-shift-action="next" aria-label="Next '+state.plannerMode+'">›</button></div><div class="button-row"><button class="'+(state.plannerMode==='week'?'primary-button':'secondary-button')+'" data-shift-action="week">Week</button><button class="'+(state.plannerMode==='month'?'primary-button':'secondary-button')+'" data-shift-action="month">Month</button><button class="secondary-button" data-shift-action="today">Today</button></div>'+
      '<label class="field">Jump to date<input type="date" data-shift-jump value="'+esc(state.plannerAnchor)+'"></label>'+
      '<div class="restored-planner-stats"><span><strong>'+esc(fmtHours(t.hours))+'</strong> scheduled</span><span><strong>'+shifts.length+'</strong> shifts</span>'+(t.contracted?'<span><strong>'+esc(fmtHours(t.overtime))+'</strong> overtime</span>':'')+(t.pay?'<span><strong>£'+t.pay.toFixed(2)+'</strong> estimated pay</span>':'')+'</div></div>'+
      (state.shiftPlannerError?'<div class="card planner-error" role="alert">'+esc(state.shiftPlannerError)+'<button class="secondary-button" data-shift-action="retry">Retry</button></div>':'')+
      (state.shiftPlannerLoading?'<p class="empty" role="status">Loading planner…</p>':'')+
      '<div class="button-row restored-planner-actions"><button class="primary-button" data-shift-action="add">＋ Add shift</button><button class="secondary-button" data-shift-action="leave">Book annual leave</button><button class="secondary-button" data-shift-action="patterns">Manage patterns</button></div>'+
      (state.shiftPlannerModal==='add'?formMarkup():state.shiftPlannerModal==='edit'?formMarkup(state.shiftPlannerEdit||{}):state.shiftPlannerModal==='leave'?leaveForm():state.shiftPlannerModal==='patterns'?patternManager():'')+
      (state.plannerMode==='week'?'<div class="restored-week-list">'+list+'</div>':list)+
      '<p class="helper">Shifts are checked for overlaps and clashes with your existing Align and imported calendar events.</p></section>';
  }
  async function reload() {
    state.shiftPlannerData=null; state.shiftPlannerError=''; await load();
  }
  function formObject(form) { return Object.fromEntries(new FormData(form).entries()); }
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-shift-action],[data-shift-date]');
    if(!button)return;
    if(button.dataset.shiftDate){state.plannerAnchor=state.plannerMode==='month'?button.dataset.shiftDate:monday(button.dataset.shiftDate);state.shiftPlannerModal='';await reload();return;}
    const action=button.dataset.shiftAction;
    if(!action)return;
    event.preventDefault();
    try {
      if(action==='previous'||action==='next'){
        state.plannerAnchor=state.plannerMode==='month'
          ? (d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-01')(new Date(state.plannerAnchor.slice(0,7)+'-01T12:00:00').constructor===Date?new Date(new Date(state.plannerAnchor.slice(0,7)+'-01T12:00:00').getFullYear(),new Date(state.plannerAnchor.slice(0,7)+'-01T12:00:00').getMonth()+(action==='next'?1:-1),1):new Date())
          : shiftDay(state.plannerAnchor,(action==='next'?7:-7));
        await reload();return;
      }
      if(action==='week'||action==='month'){state.plannerMode=action;state.plannerAnchor=action==='week'?monday(state.plannerAnchor):state.plannerAnchor.slice(0,7)+'-01';await reload();return;}
      if(action==='today'){state.plannerAnchor=state.plannerMode==='week'?monday(getToday()):getToday().slice(0,7)+'-01';await reload();return;}
      if(action==='add'){state.shiftPlannerModal='add';state.shiftPlannerEdit=null;render();return;}
      if(action==='leave'){state.shiftPlannerModal='leave';render();return;}
      if(action==='patterns'){state.shiftPlannerModal='patterns';render();return;}
      if(action==='close-form'){state.shiftPlannerModal='';render();return;}
      if(action==='retry'){await reload();return;}
      if(action==='edit'){
        const s=selectedShifts().find(item=>String(item.id)===String(button.dataset.id));
        if(s){state.shiftPlannerEdit={...s};state.shiftPlannerModal='edit';render();}
        return;
      }
      if(action==='delete'){
        if(!confirm('Delete this shift?'))return;
        await api('/api/shifts/'+button.dataset.id,{method:'DELETE'}); if(typeof toast==='function')toast('Shift deleted.'); await reload();return;
      }
      if(action==='delete-leave'){
        if(!confirm('Remove this annual leave day?'))return;
        await api('/api/annual-leave/'+button.dataset.id,{method:'DELETE'});if(typeof toast==='function')toast('Annual leave removed.');await reload();return;
      }
    } catch(e) { state.shiftPlannerError=e.message||'Planner action failed.';render(); }
  });
  document.addEventListener('change',async event=>{
    if(event.target.matches('[data-shift-jump]')){state.plannerAnchor=state.plannerMode==='week'?monday(event.target.value):event.target.value.slice(0,7)+'-01';await reload();}
    const select=event.target.closest('select[name="template_id"]');
    if(select){
      const template=(state.shiftPlannerData?.templates||[]).find(t=>String(t.id)===String(select.value));
      const form=select.closest('form');if(template&&form){
        form.elements.start_time.value=template.start_time;form.elements.end_time.value=template.end_time;form.elements.break_minutes.value=template.break_minutes;
        form.elements.location_id.value=template.location_id;form.elements.shift_type_id.value=template.shift_type_id;
      }
    }
  });
  document.addEventListener('submit',async event=>{
    const form=event.target.closest('[data-shift-form]');if(!form)return;
    event.preventDefault();
    try {
      const values=formObject(form), kind=form.dataset.shiftForm;
      if(kind==='shift'){
        const id=form.dataset.id;
        if(id) await api('/api/shifts/'+id,{method:'PUT',body:values});
        else await api('/api/shifts',{method:'POST',body:values});
        if(typeof toast==='function')toast(id?'Shift updated.':'Shift saved.');
      } else if(kind==='leave'){
        await api('/api/annual-leave',{method:'POST',body:values});if(typeof toast==='function')toast('Annual leave booked.');
      } else if(kind==='location'){
        await api('/api/locations',{method:'POST',body:values});if(typeof toast==='function')toast('Location added.');
      } else if(kind==='type'){
        await api('/api/shift-types',{method:'POST',body:values});if(typeof toast==='function')toast('Shift type added.');
      } else if(kind==='template'){
        await api('/api/templates',{method:'POST',body:values});if(typeof toast==='function')toast('Shift pattern saved.');
      }
      state.shiftPlannerModal='';await reload();
    } catch(e) { state.shiftPlannerError=e.message||'Could not save planner changes.';render(); }
  });
  window.renderShiftPlanner=render;
  window.reloadShiftPlanner=reload;
})();
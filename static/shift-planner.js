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
      const path=state.plannerMode==='week'
        ? '/api/week?start='+encodeURIComponent(state.plannerAnchor)
        : '/api/month?month='+encodeURIComponent(state.plannerAnchor.slice(0,7));
      state.shiftPlannerData=await api(path);
      await loadInboundPlannerJourneys(state.shiftPlannerData);
    } catch(e) {
      state.shiftPlannerError=e.message||'Could not load your shift planner.';
    } finally {
      state.shiftPlannerLoading=false;
      paint();
    }
  }
  async function loadInboundPlannerJourneys(data) {
    const all=[...(data.shifts||[]).map(x=>Object.assign(x,{_plannerKind:'shift'})),...(data.events||[]).map(x=>Object.assign(x,{_plannerKind:'event'})),...(data.imported_events||[]).map(x=>Object.assign(x,{_plannerKind:'imported'}))]
      .filter(x=>String(x.location||x.address||'').trim()&&!x.all_day&&plannerItemStart(x));
    const byDay=new Map();
    for(const item of all){const day=plannerItemStart(item).slice(0,10);if(day)byDay.set(day,true);}
    const days=[...byDay.keys()].filter(day=>day>=getToday()).sort().slice(0,state.plannerMode==='month'?35:7);
    await Promise.all(days.map(async day=>{
      const daily=all.filter(item=>plannerItemStart(item).slice(0,10)===day).sort((a,b)=>plannerItemStart(a).localeCompare(plannerItemStart(b)));
      let previousEnd=null,previousKey='';
      for(let i=0;i<daily.length;){
        const first=daily[i],key=plannerLocationKey(first),group=[first];let j=i+1;
        while(j<daily.length&&key&&plannerLocationKey(daily[j])===key){group.push(daily[j]);j++;}
        const start=new Date(plannerItemStart(first)),gap=previousEnd?start.getTime()-previousEnd.getTime():Infinity;
        if(start.getTime()>Date.now()&&(!previousEnd||(key!==previousKey&&gap>3600000))){
          try{
            const result=await api('/api/personal/journey',{method:'POST',body:{destination:String(first.location||first.address).trim(),arrival:plannerItemStart(first),mode:data.preferences?.default_travel||undefined}});
            if(result?.notes){const steps=result.steps||[];first.pre_travel={...result,notes:'[Align travel]\\n'+result.notes+'\\n[/Align travel]'+(steps.length?'\\n[Align travel steps]\\n'+JSON.stringify(steps)+'\\n[/Align travel steps]':'')};}
          }catch(error){first.pre_travel_error=error.message||'Inbound journey unavailable';}
        }
        previousEnd=new Date(plannerItemEnd(group[group.length-1]));
        previousKey=key;
        i=j;
      }
      // Plan the outbound leg after the final item at each workplace/location.
      // The API chooses the next event within an hour, otherwise the saved home address.
      const legs=daily.filter((item,index)=>{
        const key=plannerLocationKey(item);
        if(key&&daily[index+1]&&plannerLocationKey(daily[index+1])===key)return false;
        const end=plannerItemEnd(item);
        return !!(item.location&&!item.all_day&&end&&new Date(end).getTime()>Date.now());
      });
      await Promise.all(legs.map(async item=>{
        const kind=item._plannerKind==='shift'?'shift':item._plannerKind==='imported'?'calendar':'event';
        try{
          item.post_travel=await api('/api/personal/post-event-travel',{method:'POST',body:{
            kind,id:Number(item.id),enabled:true,mode:item.post_travel?.mode||data.preferences?.default_travel||'transit',plan:true
          }});
        }catch(error){item.post_travel_error=error.message||'Outbound journey unavailable';}
      }));
    }));
  }
  function selectedShifts() {
    const data=state.shiftPlannerData||{};
    return (data.shifts||[]).slice().sort((a,b)=>(a.work_date+a.start_time).localeCompare(b.work_date+b.start_time));
  }
  function shiftPeriod(time) { return String(time||'00:00') < '12:00' ? 'AM' : 'PM'; }
  function shiftsForDate(day, excludeId) {
    const rows=state.shiftPlannerDateShifts?.day===day
      ? state.shiftPlannerDateShifts.shifts
      : (state.shiftPlannerData?.shifts||[]);
    return rows.filter(s=>s.work_date===day && (excludeId==null || String(s.id)!==String(excludeId)));
  }
  function availableTemplatesForDate(day, excludeId) {
    const used=new Set(shiftsForDate(day,excludeId).map(s=>shiftPeriod(s.start_time)));
    return (state.shiftPlannerData?.templates||[]).filter(t=>t.active!==0 && !used.has(shiftPeriod(t.start_time)));
  }
  function shiftTypesForLocation(locationId) {
    const data=state.shiftPlannerData||{};
    const templates=(data.templates||[]).filter(t=>t.active!==0 && String(t.location_id)===String(locationId||''));
    const ids=new Set(templates.map(t=>String(t.shift_type_id)));
    const matching=(data.shift_types||[]).filter(t=>ids.has(String(t.id)));
    // If no patterns have been configured for this workplace yet, allow manual shift setup.
    return matching.length ? matching : (data.shift_types||[]);
  }
  function shiftTypeOptionsMarkup(locationId, selectedId) {
    const options=locationId ? shiftTypesForLocation(locationId) : [];
    return '<option value="">'+(locationId?(options.length?'Choose shift type':'No shift types configured'):'Choose a workplace first')+'</option>'+
      options.map(t=>'<option value="'+esc(t.id)+'" '+(String(selectedId||'')===String(t.id)?'selected':'')+'>'+esc(t.name)+'</option>').join('');
  }
  function selectedShiftDays(form) {
    return [...form.querySelectorAll('[name="selected_days"]:checked')].map(input=>input.value).sort();
  }
  function addShiftDaysMarkup(day, selectedDays) {
    const start=monday(day), chosen=new Set(selectedDays||[day]);
    return '<div class="field add-shift-days-field"><span class="field-label">Select days to add shifts</span><p class="helper">Choose every day this shift should be added to. You only need to set the workplace and shift once.</p><div class="add-shift-days-grid">'+Array.from({length:7},(_,i)=>{
      const date=shiftDay(start,i), label=fmtDay(date);
      return '<label class="add-shift-day-option"><input type="checkbox" name="selected_days" value="'+date+'" '+(chosen.has(date)?'checked':'')+'><span><strong>'+esc(label.split(' ')[0])+'</strong><small>'+esc(date.slice(8,10)+'/'+date.slice(5,7))+'</small></span></label>';
    }).join('')+'</div></div>';
  }
  function templateOptionsMarkup(day, editId, selectedId, locationId, shiftTypeId, days, period) {
    const selectedDays=(Array.isArray(days)?days:[day]).filter(Boolean);
    let options=selectedDays.length?availableTemplatesForDate(selectedDays[0],editId):[];
    for(const date of selectedDays.slice(1)){
      const available=new Set(availableTemplatesForDate(date,editId).map(t=>String(t.id)));
      options=options.filter(t=>available.has(String(t.id)));
    }
    options=options.filter(t=>
      (!locationId || String(t.location_id)===String(locationId)) &&
      (!shiftTypeId || String(t.shift_type_id)===String(shiftTypeId)) &&
      (!period || shiftPeriod(t.start_time)===period)
    );
    const prompt=!selectedDays.length?'Select at least one day first':!locationId?'Choose a workplace first':!shiftTypeId?'Choose a shift type first':options.length?'Choose a saved shift pattern':'No matching '+(period||'')+' patterns are available on every selected day';
    return '<option value="">'+prompt+'</option>'+
      options.map(t=>'<option value="'+esc(t.id)+'" '+(String(selectedId||'')===String(t.id)?'selected':'')+'>'+esc(t.label+' ('+t.start_time+'–'+t.end_time+')')+'</option>').join('');
  }
  function pmShiftMarkup(day, locationId, typeId, days, startTime) {
    const enabled=!!locationId&&!!typeId&&shiftPeriod(startTime||'09:00')==='AM';
    return '<div class="add-pm-shift-wrap"><label class="add-pm-shift-toggle"><input type="checkbox" name="add_pm_shift" value="1" data-add-pm-shift '+(!enabled?'disabled':'')+'><span><strong>Add PM shift as well</strong><small>Automatically add an afternoon shift on the same selected days</small></span></label>'+
      '<div class="add-pm-shift-fields" data-pm-shift-fields hidden>'+
      '<label class="field">PM shift pattern<select name="pm_template_id" data-pm-template disabled>'+templateOptionsMarkup(day,null,'',locationId,typeId,days,'PM')+'</select></label>'+
      '<div class="form-grid"><label class="field">PM start time<input type="time" name="pm_start_time" step="900" value="13:00" disabled></label>'+
      '<label class="field">PM end time<input type="time" name="pm_end_time" step="900" value="17:00" disabled></label>'+
      '<label class="field">PM break (minutes)<input type="number" name="pm_break_minutes" min="0" max="720" value="0" disabled></label></div></div></div>';
  }
  function dayItems(data, day) {
    const shifts=(data.shifts||[]).filter(s=>s.work_date===day);
    const events=[...(data.events||[]),...(data.imported_events||[]),...visibleFinance(data)]
      .filter(e=>String(e.start_at||'').slice(0,10)<=day && String(e.end_at||'').slice(0,10)>=day);
    const leave=(data.annual_leave||[]).filter(l=>l.leave_date===day);
    return {shifts,events,leave,total:shifts.length+events.length+leave.length};
  }
  function restGapWarnings(shifts, minimumHours) {
    const minimum=Number(minimumHours||0);
    if(minimum<=0)return [];
    const bounds=shifts.filter(s=>s.work_date&&s.start_time&&s.end_time).map(s=>{
      const start=new Date(s.work_date+'T'+s.start_time+':00');
      let end=new Date(s.work_date+'T'+s.end_time+':00');
      if(end<=start)end=new Date(end.getTime()+86400000);
      return {start,end,location:s.location_name||'Shift'};
    }).sort((a,b)=>a.start-b.start);
    const warnings=[];
    for(let i=1;i<bounds.length;i++){
      const gap=(bounds[i].start-bounds[i-1].end)/3600000;
      if(gap>=0&&gap<minimum)warnings.push('Only '+gap.toFixed(1)+' hours between shifts at '+bounds[i-1].location+' and '+bounds[i].location+'; your minimum rest is '+minimum+' hours.');
    }
    return warnings;
  }
  function totals(shifts) {
    const counted=shifts.filter(s=>!String(s.notes||'').includes('[Align cover: given'));
    const hours=counted.reduce((n,s)=>n+Number(s.hours||0),0);
    const settings=state.shiftPlannerData?.work_settings||state.boot?.settings||{};
    const contracted=Number(settings.contracted_hours||0), rate=Number(settings.rate_of_pay||0);
    const overtime=contracted>0?Math.max(0,hours-contracted):0;
    return {hours,contracted,overtime,pay:rate>0?hours*rate:0};
  }
  function shiftCard(s, options={}) {
    const travel='';
    const notes=String(s.notes||'').replace(/\[Align travel(?: steps)?\][\s\S]*?(?:\[\/Align travel(?: steps)?\]|$)/ig,'').replace(/\[Align travel pending\]/ig,'').trim();
    return '<article class="card restored-shift-card" style="--shift-colour:'+esc(s.location_colour||s.colour||'#365CE6')+'">'+
      '<div class="shift-area-panel" style="--area-colour:'+esc(s.shift_type_colour||'#6479D8')+'"><div class="restored-shift-top"><div><h3>'+esc(s.shift_type_name||'Work')+'</h3>'+(options.hideLocation?'':'<p>'+esc(s.location_name||'')+(s.location?' · '+esc(s.location):'')+'</p>')+'</div>'+
      '<span class="restored-shift-hours">'+esc(fmtHours(s.hours))+'</span></div>'+
      '<p class="restored-shift-time">'+esc(s.start_time)+'–'+esc(s.end_time)+(Number(s.break_minutes)?' · '+esc(s.break_minutes)+' min break':'')+'</p></div>'+
      (travel?'<div class="shift-travel-summary">'+travel+'</div>':'')+
      '<div class="button-row"><button class="secondary-button" data-shift-action="edit" data-id="'+esc(s.id)+'">Edit shift</button><button class="secondary-button" data-shift-action="travel" data-id="'+esc(s.id)+'">Travel after shift</button><button class="secondary-button" data-shift-action="delete" data-id="'+esc(s.id)+'">Delete</button></div></article>';
  }
  function shiftCardsMarkup(shifts) {
    const ordered=[...(shifts||[])].sort((a,b)=>(a.work_date||'').localeCompare(b.work_date||'')||(a.start_time||'').localeCompare(b.start_time||''));
    return ordered.map((s,i)=>{
      const prev=ordered[i-1];
      const sameLocation=!!prev&&String(prev.location_id||prev.location_name||'').toLowerCase()===String(s.location_id||s.location_name||'').toLowerCase();
      return shiftCard(s,{hideTravel:sameLocation});
    }).join('');
  }
  function visibleFinance(data) {
    return data.finance_calendar && data.finance_calendar.visible === false ? [] : (data.finance_events || []);
  }
  function financeCard(entry) {
    return '<article class="card"><strong>'+esc(entry.title||'Finance')+'</strong><p class="helper">Finance calendar</p><button class="text-button" type="button" data-action="finance">Open finance</button></article>';
  }
  function plannerCleanEventNotes(notes) {
    return String(notes||'')
      .replace(/\n?\[Align travel steps\][\s\S]*?(?:\[\/Align travel steps\]|$)/ig,'')
      .replace(/\n?\[Align travel\][\s\S]*?(?:\[\/Align travel\]|$)/ig,'')
      .trim();
  }
  function eventCard(e, imported=false, options={}) {
    const start=String(e.start_at||''), end=String(e.end_at||'');
    const allDay=!!Number(e.all_day);
    const when=allDay?'All day':(start.slice(11,16)||'')+(end.slice(11,16)?'–'+end.slice(11,16):'');
    const category=e.section_name||e.category_name||(imported?'Imported calendar':'Event');
    const packed=encodeURIComponent(JSON.stringify({...e,origin:imported?'Calendar':'Event'}));
    const colour=e.section_colour||e.colour||'#365CE6';
    const travel='';
    return '<article class="card restored-event-card location-bracket-card" style="--location-colour:'+esc(colour)+';--area-colour:'+esc(colour)+'"><button type="button" class="restored-event-open" data-shift-action="view-event" data-event-data="'+esc(packed)+'"><div class="restored-event-top"><span class="restored-event-mark">'+(imported?'▦':'•')+'</span><div><strong>'+esc(e.title||'Event')+'</strong><p>'+esc(category)+(e.location?' · '+esc(e.location):'')+'</p></div></div><p class="restored-event-time">'+esc(when)+'</p>'+(e.location?'<small class="restored-event-address">'+esc(e.location)+'</small>':'')+(plannerCleanEventNotes(e.notes)?'<p class="planner-event-detail">'+esc(plannerCleanEventNotes(e.notes))+'</p>':'<span class="helper">View details</span>')+'</button><div class="button-row">'+(!imported&&e.section_id&&e.id?'<button class="secondary-button" data-shift-action="edit-event" data-event-data="'+esc(packed)+'">Edit event</button>':'')+'<button class="secondary-button" data-nav="sections">Manage events</button></div></article>';
  }
  function leaveCard(l) {
    return '<article class="card restored-leave-card"><div><strong>Annual leave</strong><p>'+esc(fmtDay(l.leave_date))+(l.notes?' · '+esc(l.notes):'')+'</p></div><button class="secondary-button" data-shift-action="delete-leave" data-id="'+esc(l.id)+'">Remove</button></article>';
  }
  function formMarkup(edit={}) {
    const data=state.shiftPlannerData||{};
    const locations=data.locations||[], types=data.shift_types||[];
    const day=edit.work_date||state.shiftPlannerSelectedDay||state.plannerAnchor||getToday();
    const templates=availableTemplatesForDate(day,edit.id);
    const template=templates.find(t=>String(t.id)===String(edit.template_id||''))||
      (edit.id?(data.templates||[]).find(t=>String(t.id)===String(edit.template_id||'')):null)||null;
    const chosenLocation=edit.location_id||template?.location_id||'';
    const chosenType=edit.shift_type_id||template?.shift_type_id||'';
    const used=shiftsForDate(day,edit.id);
    const usedPeriods=[...new Set(used.map(s=>shiftPeriod(s.start_time)))];
    const periodNote=usedPeriods.length?usedPeriods.map(p=>p+' shift already planned').join(' · ')+'. Only the other period is available.':'Choose an AM or PM pattern. You can add the other period afterwards.';
    const initialDays=edit.id?[]:[state.shiftPlannerSelectedDay||day];
    return '<section class="card restored-planner-form" id="shift-planner-form"><div class="section-head"><div><p class="eyebrow">'+(edit.id?'Edit shift':'Plan a shift')+'</p><h2>'+(edit.id?'Update shift':'Add shifts')+'</h2></div><button class="secondary-button" data-shift-action="close-form">Close</button></div>'+
      '<form data-shift-form="shift" data-id="'+esc(edit.id||'')+'">'+
      (edit.id?'<label class="field">Work date<input type="date" name="work_date" data-shift-work-date required value="'+esc(day)+'"></label>':addShiftDaysMarkup(day,initialDays))+
      '<label class="field">Choose where<select name="location_id" data-shift-location required><option value="">Choose a workplace</option>'+locations.map(l=>'<option value="'+esc(l.id)+'" '+(String(chosenLocation)===String(l.id)?'selected':'')+'>'+esc(l.name)+'</option>').join('')+'</select></label>'+
      '<label class="field">Choose shift type<select name="shift_type_id" data-shift-type required '+(!chosenLocation?'disabled':'')+'>'+shiftTypeOptionsMarkup(chosenLocation,chosenType)+'</select></label>'+
      '<label class="field">Choose shift pattern<select name="template_id" data-shift-template '+(!chosenLocation||!chosenType?'disabled':'')+'>'+templateOptionsMarkup(day,edit.id,template?.id,chosenLocation,chosenType,initialDays)+'</select></label>'+
      '<p class="helper" data-shift-period-note>'+esc(periodNote)+'</p>'+
      '<div class="form-grid"><label class="field">Start time<input type="time" name="start_time" step="900" required value="'+esc(edit.start_time||template?.start_time||'09:00')+'"></label>'+
      '<label class="field">End time<input type="time" name="end_time" step="900" required value="'+esc(edit.end_time||template?.end_time||'13:00')+'"></label>'+
      '<label class="field">Break (minutes)<input type="number" name="break_minutes" min="0" max="720" value="'+esc(edit.break_minutes??template?.break_minutes??0)+'"></label></div>'+
      (edit.id?'':pmShiftMarkup(day,chosenLocation,chosenType,initialDays,edit.start_time||template?.start_time||'09:00'))+
      '<label class="field">Notes<textarea name="notes" rows="2">'+esc(edit.notes||'')+'</textarea></label>'+
      '<div class="button-row"><button class="primary-button" type="submit">'+(edit.id?'Save changes':'Add shifts to selected days')+'</button></div></form></section>';
  }
  function leaveForm() {
    return '<section class="card restored-planner-form"><div class="section-head"><div><p class="eyebrow">Time off</p><h2>Book annual leave</h2></div><button class="secondary-button" data-shift-action="close-form">Close</button></div>'+
      '<form data-shift-form="leave"><div class="form-grid"><label class="field">First day<input name="start_date" type="date" required value="'+esc(state.plannerAnchor||getToday())+'"></label><label class="field">Last day<input name="end_date" type="date" required value="'+esc(state.plannerAnchor||getToday())+'"></label></div><label class="field">Notes<textarea name="notes" rows="2"></textarea></label><button class="primary-button" type="submit">Book leave</button></form></section>';
  }
  function patternManager() {
    const d=state.shiftPlannerData||{};
    return '<section class="card restored-planner-form"><div class="section-head"><div><p class="eyebrow">Setup</p><h2>Locations, shift types and saved patterns</h2></div><button class="secondary-button" data-shift-action="close-form">Close</button></div>'+
      '<form data-shift-form="location"><h3>Add work location</h3><label class="field">Name<input name="name" required></label>'+addressFields('shift-location-address','address','','Address (optional)')+'<button class="secondary-button" type="submit">Add location</button></form><hr>'+
      '<form data-shift-form="type"><h3>Add shift type</h3><label class="field">Name<input name="name" required placeholder="e.g. Wards, Clinic"></label><button class="secondary-button" type="submit">Add shift type</button></form><hr>'+
      '<form data-shift-form="template"><h3>Save shift pattern</h3><label class="field">Pattern name<input name="label" required placeholder="e.g. AM clinic"></label><div class="form-grid"><label class="field">Location<select name="location_id" required><option value="">Choose location</option>'+(d.locations||[]).map(l=>'<option value="'+esc(l.id)+'">'+esc(l.name)+'</option>').join('')+'</select></label><label class="field">Shift type<select name="shift_type_id" required><option value="">Choose type</option>'+(d.shift_types||[]).map(t=>'<option value="'+esc(t.id)+'">'+esc(t.name)+'</option>').join('')+'</select></label><label class="field">Start<input type="time" name="start_time" value="09:00" required></label><label class="field">End<input type="time" name="end_time" value="13:00" required></label><label class="field">Break (minutes)<input type="number" name="break_minutes" min="0" value="0"></label></div><button class="primary-button" type="submit">Save pattern</button></form></section>';
  }
  function calendarMarkup(data) {
    const month=state.plannerAnchor.slice(0,7), first=new Date(month+'-01T12:00:00');
    const count=new Date(first.getFullYear(),first.getMonth()+1,0).getDate(), offset=(first.getDay()+6)%7;
    const shifts=data.shifts||[], leaves=data.annual_leave||[], events=[...(data.events||[]),...(data.imported_events||[]),...visibleFinance(data)];
    let cells=Array.from({length:offset},()=>'<span class="restored-month-empty"></span>').join('');
    for(let i=1;i<=count;i++){
      const day=month+'-'+String(i).padStart(2,'0'), n=shifts.filter(s=>s.work_date===day).length, leave=leaves.some(l=>l.leave_date===day);
      const eventCount=events.filter(e=>String(e.start_at||'')<day+'T23:59:59' && String(e.end_at||'')>day+'T00:00').length;
      const total=n+eventCount+(leave?1:0);
      cells+='<button class="restored-month-day '+(day===getToday()?'is-today ':'')+(n?'has-shifts ':'')+(leave?'has-leave ':'')+(eventCount?'has-events':'')+'" data-shift-date="'+day+'"><span>'+i+'</span>'+(total?'<small>'+total+' total item'+(total===1?'':'s')+'</small>':'')+(n?'<small>'+n+' shift'+(n===1?'':'s')+'</small>':'')+(leave?'<small>Leave</small>':'')+'</button>';
    }
    return '<div class="restored-month-grid">'+['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d=>'<span class="restored-month-heading">'+d+'</span>').join('')+cells+'</div>';
  }
  function plannerLocationKey(item) {
    const address=String(item.location||item.address||'').trim().toLocaleLowerCase().replace(/\s+/g,' ');
    if(address)return 'address:'+address;
    const id=item.location_id||item.place_id;
    if(id)return 'id:'+id;
    if(item._plannerKind==='leave')return '';
    return 'unlocated:'+(item._plannerKind||'item')+':'+(item.id||item.start_at||item.work_date||item.title||'unknown');
  }
  function plannerItemStart(item) {
    return item.work_date ? item.work_date+'T'+(item.start_time||'00:00') : String(item.start_at||'');
  }
  function plannerItemEnd(item) {
    return item.work_date ? item.work_date+'T'+(item.end_time||item.start_time||'00:00') : String(item.end_at||item.start_at||'');
  }
  function plannerItemHours(item) {
    const value=Number(item.hours);
    if(Number.isFinite(value)&&value>0)return value;
    const start=new Date(plannerItemStart(item)),end=new Date(plannerItemEnd(item));
    return Number.isFinite(start.getTime())&&Number.isFinite(end.getTime())?Math.max(0,(end-start)/3600000):0;
  }
  function plannerItemCard(item,options={}) {
    if(item._plannerKind==='shift')return shiftCard(item,{hideLocation:true});
    if(item._plannerKind==='imported')return eventCard(item,true,{hideLocation:true});
    if(item._plannerKind==='event')return eventCard(item,false,{hideLocation:true});
    if(item._plannerKind==='finance')return financeCard(item);
    return leaveCard(item);
  }
  function locationGroupsMarkup(items) {
    const ordered=[...(items||[])].sort((a,b)=>plannerItemStart(a).localeCompare(plannerItemStart(b)));
    const chunks=[];
    for(let i=0;i<ordered.length;){
      const item=ordered[i],key=plannerLocationKey(item);
      if(!key){chunks.push(plannerItemCard(item));i++;continue;}
      const group=[item];let j=i+1;
      while(j<ordered.length&&plannerLocationKey(ordered[j])===key){group.push(ordered[j]);j++;}
      const first=group[0],last=group[group.length-1];
      const title=first.location_name||first.place_name||first.location_label||first.location||first.address||'Location not set';
      const address=first.location||first.address||'';
      const colour=first.location_colour||first.colour||first.section_colour||'#365CE6';
      const start=plannerItemStart(first).slice(11,16),end=plannerItemEnd(last).slice(11,16);
      const hours=group.reduce((sum,x)=>sum+plannerItemHours(x),0);
      const areas=group.map(x=>{
        const area=x.shift_type_name||x.section_name||x.category_name||x.title||x.name||'Event';
        const areaColour=x.shift_type_colour||x.section_colour||x.colour||'#16A99B';
        return '<div class="location-group-area" style="--area-colour:'+esc(areaColour)+'">'+plannerItemCard(x)+'</div>';
      }).join('');
      let travel='';
      if(typeof eventTravelMarkup==='function'){
        const candidate={...last,origin:last._plannerKind==='shift'?'Shift':last._plannerKind==='imported'?'Calendar':'Event'};
        travel=eventTravelMarkup(candidate,{includeInbound:false})||'';
      }
      const inbound=first.pre_travel?(typeof travelRouteStrip==='function'?'<div class="planner-inbound-travel">'+travelRouteStrip(first.pre_travel)+'</div>':(typeof journeyEventSummary==='function'?'<div class="planner-inbound-travel">'+journeyEventSummary(first.pre_travel.notes)+'</div>':'')):'';
      chunks.push('<section class="planner-location-group" style="--location-colour:'+esc(colour)+'"><header class="planner-location-header"><div><strong>'+esc(title)+'</strong>'+(address?'<small>'+esc(address)+'</small>':'')+'<small>'+hours.toFixed(Number.isInteger(hours)?0:1)+' hours · '+group.length+' item'+(group.length===1?'':'s')+'</small></div><strong>'+esc(start)+'–'+esc(end)+'</strong></header>'+inbound+'<div class="planner-location-areas">'+areas+'</div></section>'+(travel?'<div class="planner-location-travel">'+travel+'</div>':''));
      i=j;
    }
    return chunks.join('');
  }
  function plannerDayMarkup(shifts,events,imported,finance,leave) {
    const items=[
      ...(shifts||[]).map(x=>({...x,_plannerKind:'shift'})),
      ...(events||[]).map(x=>({...x,_plannerKind:'event'})),
      ...(imported||[]).map(x=>({...x,_plannerKind:'imported'})),
      ...(finance||[]).map(x=>({...x,_plannerKind:'finance'})),
      ...(leave||[]).map(x=>({...x,_plannerKind:'leave'}))
    ];
    return locationGroupsMarkup(items);
  }
  function renderMonthList(data) {
    const month=state.plannerAnchor.slice(0,7);
    const first=new Date(month+'-01T12:00:00');
    const count=new Date(first.getFullYear(),first.getMonth()+1,0).getDate();
    const shifts=data.shifts||[], leaves=data.annual_leave||[];
    const events=[...(data.events||[]),...(data.imported_events||[]),...visibleFinance(data)];
    const rows=[];
    for(let i=1;i<=count;i++){
      const day=month+'-'+String(i).padStart(2,'0');
      const ds=shifts.filter(s=>s.work_date===day), ls=leaves.filter(l=>l.leave_date===day);
      const es=events.filter(e=>e.origin!=='Finance'&&String(e.start_at||'')<day+'T23:59:59'&&String(e.end_at||'')>day+'T00:00');
      const fes=visibleFinance(data).filter(e=>String(e.start_at||'').slice(0,10)===day);
      if(!ds.length&&!ls.length&&!es.length&&!fes.length)continue;
      rows.push('<section class="restored-planner-day"><h3>'+esc(fmtDay(day))+' · '+(ds.length+es.length+fes.length+ls.length)+' total item'+(ds.length+es.length+fes.length+ls.length===1?'':'s')+'</h3>'+plannerDayMarkup(ds,es.filter(e=>!(e.origin==='Calendar')&&!!e.section_name),es.filter(e=>(e.origin==='Calendar')||(!e.section_name&&!!e.category_name)),fes,ls)+'</section>');
    }
    return rows.length?'<div class="restored-week-list">'+rows.join('')+'</div>':'<p class="empty">Nothing planned this month.</p>';
  }
  function render() {
    init();
    if (!state.shiftPlannerData && !state.shiftPlannerLoading && !state.shiftPlannerError) { void load(); }
    const d=state.shiftPlannerData||{shifts:[],annual_leave:[],templates:[],locations:[],shift_types:[]};
    const shifts=selectedShifts(), leaves=(d.annual_leave||[]).slice().sort((a,b)=>a.leave_date.localeCompare(b.leave_date));
    const t=totals(shifts);
    const restWarnings=restGapWarnings(shifts,d.work_settings?.minimum_rest_hours);
    const title=state.plannerMode==='week'?'Week commencing '+fmtDay(monday(state.plannerAnchor)):fmtMonth(state.plannerAnchor);
    const list=state.plannerMode==='week'
      ? Array.from({length:7},(_,i)=>shiftDay(monday(state.plannerAnchor),i)).map(day=>{
        const ds=shifts.filter(s=>s.work_date===day), ls=leaves.filter(l=>l.leave_date===day);
        const es=(d.events||[]).filter(e=>String(e.start_at||'')<day+'T23:59:59'&&String(e.end_at||'')>day+'T00:00');
        const ies=(d.imported_events||[]).filter(e=>String(e.start_at||'')<day+'T23:59:59'&&String(e.end_at||'')>day+'T00:00');
        const fes=visibleFinance(d).filter(e=>String(e.start_at||'').slice(0,10)===day);
        const total=ds.length+es.length+ies.length+fes.length+ls.length;
        return '<section class="restored-planner-day"><h3>'+esc(fmtDay(day))+' · '+total+' total item'+(total===1?'':'s')+'</h3>'+plannerDayMarkup(ds,es,ies,fes,ls)+(!total?'<p class="restored-rest-day">Nothing planned</p>':'')+'</section>';
      }).join('')
      : state.plannerMode==='list' ? renderMonthList(d)
      : calendarMarkup(d)+'<div class="restored-planner-list">'+plannerDayMarkup(shifts,d.events||[],d.imported_events||[],visibleFinance(d),leaves)+(!shifts.length&&!leaves.length&&!(d.events||[]).length&&!(d.imported_events||[]).length&&!visibleFinance(d).length?'<p class="empty">No shifts, events or leave this month.</p>':'')+'</div>';
    return '<section class="page planner-page restored-planner-page"><div class="add-head"><p class="eyebrow">Work schedule</p><h1>Planner</h1><p class="subtle">Your shifts, saved patterns and annual leave — together in one place.</p></div>'+
      '<div class="card restored-planner-toolbar"><div class="schedule-week-nav"><button class="secondary-button" data-shift-action="previous" aria-label="Previous '+state.plannerMode+'">‹</button><h2>'+esc(title)+'</h2><button class="secondary-button" data-shift-action="next" aria-label="Next '+state.plannerMode+'">›</button></div><div class="button-row"><button class="'+(state.plannerMode==='list'?'primary-button':'secondary-button')+'" data-shift-action="list">List</button><button class="'+(state.plannerMode==='week'?'primary-button':'secondary-button')+'" data-shift-action="week">Week</button><button class="'+(state.plannerMode==='month'?'primary-button':'secondary-button')+'" data-shift-action="month">Month</button><button class="secondary-button" data-shift-action="today">Today</button></div>'+
      '<label class="field">Jump to date<input type="date" data-shift-jump value="'+esc(state.plannerAnchor)+'"></label>'+
      '<label class="setup-check"><input type="checkbox" data-finance-calendar '+(d.finance_calendar&&d.finance_calendar.visible===false?'':'checked')+'> Show Finance calendar</label>'+
      '<div class="restored-planner-stats"><span><strong>'+esc(fmtHours(t.hours))+'</strong> scheduled</span><span><strong>'+shifts.length+'</strong> shifts</span>'+(t.contracted?'<span><strong>'+esc(fmtHours(t.overtime))+'</strong> overtime</span>':'')+(t.pay?'<span><strong>£'+t.pay.toFixed(2)+'</strong> estimated pay</span>':'')+(d.leave_balance?.allowance?'<span><strong>'+esc(d.leave_balance.remaining)+'</strong> leave days left of '+esc(d.leave_balance.allowance)+'</span>':'')+'</div></div>'+restWarnings.map(w=>'<p class="card restored-planner-warning">'+esc(w)+'</p>').join('')+
      (state.shiftPlannerError?'<div class="card planner-error" role="alert">'+esc(state.shiftPlannerError)+'<button class="secondary-button" data-shift-action="retry">Retry</button></div>':'')+
      (state.shiftPlannerLoading?'<p class="empty" role="status">Loading planner…</p>':'')+
      '<div class="button-row restored-planner-actions"><button class="primary-button" data-shift-action="add">＋ Add shift</button><button class="secondary-button" data-shift-action="leave">Book annual leave</button><button class="secondary-button" data-shift-action="patterns">Manage patterns</button><button class="secondary-button" data-shift-action="work-settings">Work settings</button><button class="secondary-button" data-shift-action="settings">Planner settings</button><button class="secondary-button" data-nav="sections">Manage events</button></div>'+
      (state.shiftPlannerModal==='add'?formMarkup():state.shiftPlannerModal==='edit'?formMarkup(state.shiftPlannerEdit||{}):state.shiftPlannerModal==='leave'?leaveForm():state.shiftPlannerModal==='patterns'?patternManager():'')+
      (state.plannerMode==='week'?'<div class="restored-week-list">'+list+'</div>':list)+
      '<p class="helper">Shifts are checked for overlaps and clashes with your existing Align and imported calendar events.</p></section>';
  }
  function paint() { const root=document.querySelector('#app'); if(root && ['planner','calendar'].includes(state.tab)) root.innerHTML=render(); }
  async function reload() {
    state.shiftPlannerData=null; state.shiftPlannerDateShifts=null; state.shiftPlannerError=''; await load();
  }
  function formObject(form) { return Object.fromEntries(new FormData(form).entries()); }
  document.addEventListener('change', async event => {
    const target=event.target;
    if(target.matches('[data-finance-calendar]')){
      try {
        await api('/api/finance/settings', {method:'PATCH', body:{calendar_visible: target.checked}});
        await reload();
      } catch (error) { if (typeof toast === 'function') toast(error.message); }
      return;
    }
    const form=target.closest('[data-shift-form="shift"]');
    if(!form)return;
    if(target.matches('[data-shift-work-date]')){
      const day=target.value;
      if(!day)return;
      try{
        const result=await api('/api/shifts?start='+encodeURIComponent(day)+'&end='+encodeURIComponent(day));
        state.shiftPlannerDateShifts={day,shifts:result.shifts||[]};
        const selected=form.querySelector('[name="template_id"]')?.value||'';
        const editId=form.dataset.id||null;
        const locationId=form.querySelector('[name="location_id"]')?.value||'';
        const shiftTypeId=form.querySelector('[name="shift_type_id"]')?.value||'';
        const choices=availableTemplatesForDate(day,editId).filter(t=>
          (!locationId||String(t.location_id)===String(locationId)) &&
          (!shiftTypeId||String(t.shift_type_id)===String(shiftTypeId))
        );
        const select=form.querySelector('[name="template_id"]');
        if(select){
          select.innerHTML=templateOptionsMarkup(day,editId,choices.some(t=>String(t.id)===String(selected))?selected:'',locationId,shiftTypeId);
          select.disabled=!locationId||!shiftTypeId;
          if(!choices.some(t=>String(t.id)===String(selected))) select.value='';
        }
        const used=[...new Set(shiftsForDate(day,editId).map(s=>shiftPeriod(s.start_time)))];
        const note=form.querySelector('[data-shift-period-note]');
        if(note)note.textContent=used.length?used.map(p=>p+' shift already planned').join(' · ')+'. Only the other period is available.':'Choose an AM or PM pattern. You can add the other period afterwards.';
      }catch(error){state.shiftPlannerError=error.message||'Could not check shifts for this date.';paint();}
      return;
    }
    if(target.matches('[data-add-pm-shift]')){
      const panel=form.querySelector('[data-pm-shift-fields]');
      if(panel){panel.hidden=!target.checked;panel.querySelectorAll('input,select').forEach(field=>field.disabled=!target.checked);}
      return;
    }
    if(target.matches('[name="start_time"]')){
      const addPm=form.querySelector('[data-add-pm-shift]');
      if(addPm&&shiftPeriod(target.value)==='AM'&&form.elements.location_id.value&&form.elements.shift_type_id.value)addPm.disabled=false;
      if(addPm&&shiftPeriod(target.value)==='PM'){addPm.checked=false;addPm.disabled=true;const panel=form.querySelector('[data-pm-shift-fields]');if(panel){panel.hidden=true;panel.querySelectorAll('input,select').forEach(field=>field.disabled=true);}}
      return;
    }
    if(target.matches('[name="selected_days"]')){
      const patternSelect=form.querySelector('[name="template_id"]');
      const dates=selectedShiftDays(form);
      if(patternSelect){
        patternSelect.innerHTML=templateOptionsMarkup(dates[0]||state.shiftPlannerSelectedDay||state.plannerAnchor,form.dataset.id||null,'',form.elements.location_id.value,form.elements.shift_type_id.value,dates);
        patternSelect.disabled=!dates.length||!form.elements.location_id.value||!form.elements.shift_type_id.value;
        patternSelect.value='';
      }
      const pmPattern=form.querySelector('[data-pm-template]');
      if(pmPattern)pmPattern.innerHTML=templateOptionsMarkup(dates[0]||state.shiftPlannerSelectedDay||state.plannerAnchor||getToday(),null,'',form.elements.location_id.value,form.elements.shift_type_id.value,dates,'PM');
      const note=form.querySelector('[data-shift-period-note]');
      if(note)note.textContent=dates.length?dates.length+' day'+(dates.length===1?'':'s')+' selected. One shift setup will be applied to all selected days.':'Select at least one day to continue.';
      return;
    }
    if(target.matches('[name="location_id"]')){
      const typeSelect=form.querySelector('[name="shift_type_id"]');
      const patternSelect=form.querySelector('[name="template_id"]');
      if(typeSelect){
        typeSelect.innerHTML=shiftTypeOptionsMarkup(target.value,'');
        typeSelect.disabled=!target.value;
        typeSelect.value='';
      }
      if(patternSelect){
        const dates=form.dataset.id?[form.elements.work_date.value]:selectedShiftDays(form);
        patternSelect.innerHTML=templateOptionsMarkup(dates[0]||state.shiftPlannerSelectedDay||state.plannerAnchor||getToday(),form.dataset.id||null,'',target.value,'',dates);
        patternSelect.disabled=true;patternSelect.value='';
      }
      const pmToggle=form.querySelector('[data-add-pm-shift]');
      if(pmToggle){pmToggle.checked=false;pmToggle.disabled=true;const panel=form.querySelector('[data-pm-shift-fields]');if(panel){panel.hidden=true;panel.querySelectorAll('input,select').forEach(field=>field.disabled=true);}}
      return;
    }
    if(target.matches('[name="shift_type_id"]')){
      const patternSelect=form.querySelector('[name="template_id"]');
      if(patternSelect){
        const dates=form.dataset.id?[form.elements.work_date.value]:selectedShiftDays(form);
        patternSelect.innerHTML=templateOptionsMarkup(dates[0]||state.shiftPlannerSelectedDay||state.plannerAnchor||getToday(),form.dataset.id||null,'',form.elements.location_id.value,target.value,dates);
        patternSelect.disabled=!form.elements.location_id.value||!target.value;
        patternSelect.value='';
      }
      const pmToggle=form.querySelector('[data-add-pm-shift]');
      if(pmToggle){pmToggle.disabled=!form.elements.location_id.value||!target.value;pmToggle.checked=false;const panel=form.querySelector('[data-pm-shift-fields]');if(panel){panel.hidden=true;panel.querySelectorAll('input,select').forEach(field=>field.disabled=true);}}
      const pmPattern=form.querySelector('[data-pm-template]');
      if(pmPattern){const dates=form.dataset.id?[form.elements.work_date.value]:selectedShiftDays(form);pmPattern.innerHTML=templateOptionsMarkup(dates[0]||state.shiftPlannerSelectedDay||state.plannerAnchor||getToday(),null,'',form.elements.location_id.value,target.value,dates,'PM');}
      return;
    }
    if(target.matches('[name="template_id"]')){
      const selected=(state.shiftPlannerData?.templates||[]).find(t=>String(t.id)===String(target.value));
      if(!selected)return;
      const form=target.closest('form');
      for(const [name,value] of Object.entries({location_id:selected.location_id,shift_type_id:selected.shift_type_id,start_time:selected.start_time,end_time:selected.end_time,break_minutes:selected.break_minutes||0})){
        const field=form.querySelector('[name="'+name+'"]');if(field)field.value=value;
      }
      const pmToggle=form.querySelector('[data-add-pm-shift]');
      if(pmToggle){pmToggle.disabled=shiftPeriod(selected.start_time)!=='AM';if(pmToggle.disabled){pmToggle.checked=false;const panel=form.querySelector('[data-pm-shift-fields]');if(panel){panel.hidden=true;panel.querySelectorAll('input,select').forEach(field=>field.disabled=true);}}}
    }
    if(target.matches('[data-pm-template]')){
      const selected=(state.shiftPlannerData?.templates||[]).find(t=>String(t.id)===String(target.value));
      if(!selected)return;
      const pmForm=target.closest('form');
      for(const [name,value] of Object.entries({pm_start_time:selected.start_time,pm_end_time:selected.end_time,pm_break_minutes:selected.break_minutes||0})){
        const field=pmForm.querySelector('[name="'+name+'"]');if(field)field.value=value;
      }
    }
  });
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-shift-action],[data-shift-date]');
    if(!button)return;
    if(button.dataset.shiftDate){state.shiftPlannerSelectedDay=button.dataset.shiftDate;state.plannerAnchor=monday(button.dataset.shiftDate);state.plannerMode='week';state.shiftPlannerModal='';await reload();return;}
    const action=button.dataset.shiftAction;
    if(!action)return;
    event.preventDefault();
    try {
      if(action==='previous'||action==='next'){state.shiftPlannerSelectedDay=null;
        if(state.plannerMode!=='week'){
          const current=new Date(state.plannerAnchor.slice(0,7)+'-01T12:00:00');
          const next=new Date(current.getFullYear(),current.getMonth()+(action==='next'?1:-1),1);
          state.plannerAnchor=next.getFullYear()+'-'+String(next.getMonth()+1).padStart(2,'0')+'-01';
        } else {
          state.plannerAnchor=shiftDay(state.plannerAnchor,action==='next'?7:-7);
        }
        await reload();return;
      }
      if(action==='week'||action==='month'||action==='list'){state.shiftPlannerSelectedDay=null;state.plannerMode=action;state.plannerAnchor=action==='week'?monday(state.plannerAnchor):state.plannerAnchor.slice(0,7)+'-01';await reload();return;}
      if(action==='today'){state.plannerAnchor=state.plannerMode==='week'?monday(getToday()):getToday().slice(0,7)+'-01';await reload();return;}
      if(action==='add'){state.shiftPlannerModal='add';state.shiftPlannerEdit=null;paint();return;}
      if(action==='work-settings'){if(typeof openWorkSetup==='function')await openWorkSetup();return;}
      if(action==='settings'){state.settingsBranch='alerts';state.tab='settings';if(typeof render==='function')render();return;}
      if(action==='leave'){state.shiftPlannerModal='leave';paint();return;}
      if(action==='patterns'){state.shiftPlannerModal='patterns';paint();return;}
      if(action==='close-form'){state.shiftPlannerModal='';paint();return;}
      if(action==='retry'){await reload();return;}
      if(action==='edit-event'){
        const item=JSON.parse(decodeURIComponent(button.dataset.eventData||'%7B%7D'));
        if(item.origin==='Calendar'||!item.section_id||!item.id){if(typeof toast==='function')toast('Edit imported events in their original calendar.');return;}
        state.sectionId=Number(item.section_id);
        state.sectionData=await api('/api/sections/'+state.sectionId);
        if(typeof sectionEventModal==='function')sectionEventModal(Number(item.id));
        return;
      }
      if(action==='view-event'){
        const item=JSON.parse(decodeURIComponent(button.dataset.eventData||'%7B%7D'));
        const start=String(item.start_at||''), end=String(item.end_at||'');
        const dateLabel=start.slice(0,10)?fmtDay(start.slice(0,10)):'';
        const timeLabel=Number(item.all_day)?'All day':(start.slice(11,16)||'')+(end.slice(11,16)?'–'+end.slice(11,16):'');
        const category=item.section_name||item.category_name||(item.origin==='Calendar'?'Imported calendar':'Event');
        if(typeof modal==='function') modal(item.title||'Event','<div class="settings-form"><p><strong>'+esc(dateLabel)+'</strong></p><p>'+esc(timeLabel)+'</p><p>'+esc(category)+'</p>'+(item.location?'<p>'+esc(item.location)+'</p>':'')+(item.notes?'<p>'+esc(item.notes)+'</p>':'')+'<p class="helper">'+(item.origin==='Calendar'?'Imported calendar event. Edit it in its original calendar.':'You can edit this event from its section in Align.')+'</p><div class="button-row"><button type="button" class="primary-button" data-nav="sections">Manage events</button></div></div>');
        return;
      }
      if(action==='edit'){
        let shift=selectedShifts().find(item=>String(item.id)===String(button.dataset.id));
        if(!shift && button.dataset.workDate){
          const day=button.dataset.workDate;
          state.plannerAnchor=monday(day);
          state.plannerMode='week';
          state.shiftPlannerData=await api('/api/week?start='+encodeURIComponent(state.plannerAnchor));
          shift=selectedShifts().find(item=>String(item.id)===String(button.dataset.id));
        }
        if(shift){
          state.tab='planner';
          state.shiftPlannerEdit={...shift};
          state.shiftPlannerModal='edit';
          if(typeof render==='function')render();
          paint();
        }
        return;
      }
      if(action==='travel'){
        const id=Number(button.dataset.id);
        if(typeof modal==='function'&&typeof mountPostTravelEditor==='function'){
          modal('Travel after shift','<div class="settings-form"><p>Choose how Align should plan the journey after this shift.</p></div>');
          await mountPostTravelEditor('shift',id);
        } else if(typeof toast==='function') toast('Travel settings are not available on this screen.');
        return;
      }
      if(action==='delete'){
        if(!confirm('Delete this shift?'))return;
        await api('/api/shifts/'+button.dataset.id,{method:'DELETE'}); if(typeof toast==='function')toast('Shift deleted.'); if(['today','home'].includes(state.tab)){if(typeof refresh==='function')await refresh();}else await reload();return;
      }
      if(action==='delete-leave'){
        if(!confirm('Remove this annual leave day?'))return;
        await api('/api/annual-leave/'+button.dataset.id,{method:'DELETE'});if(typeof toast==='function')toast('Annual leave removed.');await reload();return;
      }
    } catch(e) { state.shiftPlannerError=e.message||'Planner action failed.';paint(); }
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
        if(id) {
          await api('/api/shifts/'+id,{method:'PUT',body:values});
          if(typeof toast==='function')toast('Shift updated.');
        } else {
          const days=selectedShiftDays(form);
          if(!days.length)throw new Error('Select at least one day to add shifts.');
          delete values.selected_days;
          delete values.work_date;
          const period=shiftPeriod(values.start_time);
          const addPm=form.elements.add_pm_shift?.checked===true;
          const pmValues=addPm?{location_id:values.location_id,shift_type_id:values.shift_type_id,start_time:values.pm_start_time,end_time:values.pm_end_time,break_minutes:values.pm_break_minutes||0,notes:values.notes||''}:null;
          if(addPm&&(!pmValues.start_time||!pmValues.end_time||shiftPeriod(pmValues.start_time)!=='PM'))throw new Error('Choose a valid PM shift time.');
          const conflicts=days.filter(work_date=>{
            const existing=shiftsForDate(work_date).map(shift=>shiftPeriod(shift.start_time));
            return existing.includes(period)||(addPm&&existing.includes('PM'));
          });
          if(conflicts.length)throw new Error('A shift already exists in the selected AM/PM period on '+conflicts.map(fmtDay).join(', ')+'. Remove those days or choose different days.');
          delete values.add_pm_shift;delete values.pm_template_id;delete values.pm_start_time;delete values.pm_end_time;delete values.pm_break_minutes;
          let saved=0;
          for(const work_date of days){
            try{
              await api('/api/shifts',{method:'POST',body:{...values,work_date}});saved++;
              if(addPm){await api('/api/shifts',{method:'POST',body:{...pmValues,work_date}});saved++;}
            }catch(error){
              if(saved&&typeof toast==='function')toast(saved+' shift'+(saved===1?'':'s')+' saved before '+work_date+' failed: '+(error.message||'unknown error'));
              throw error;
            }
          }
          if(typeof toast==='function')toast(saved+' shift'+(saved===1?'':'s')+' added across '+days.length+' selected day'+(days.length===1?'':'s')+(addPm?' (AM and PM).':'.'));
        }
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
    } catch(e) { state.shiftPlannerError=e.message||'Could not save planner changes.';paint(); }
  });
  window.renderShiftPlanner=render;
  window.reloadShiftPlanner=reload;
})();
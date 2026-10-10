/* Published forms and private records inside the existing Align planner. */
const builderRuntime = {layout:null, records:[], archived:false, search:'', loading:false, error:''};
function builderDocument() { return state.boot?.builder?.document; }
function builderStartup(edit=false) {
  const config=builderDocument().startup;
  return `<section class="page builder-profile"><div class="hero"><p class="eyebrow">${edit?'Your account':'First-time setup'}</p><h1>${escapeHtml(edit?'Personal details':config.title)}</h1><p class="subtle">${escapeHtml(config.description)}</p></div><form class="card settings-form" data-builder-form="profile">${AlignFields.render(config.fields,state.boot.builder.profile,'personal')}${travelFields()}<p class="helper" role="status" data-builder-error></p><button class="primary-button">${escapeHtml(edit?'Save details':config.button)}</button></form></section>`;
}
function builderMenuTiles(parent='') {
  return (builderDocument()?.menus||[]).filter(m=>m.active&&m.parent_id===parent).map(m=>`<button class="quick-action" data-builder-action="menu" data-builder-id="${escapeHtml(m.id)}" style="border-left:4px solid ${escapeHtml(m.colour)}"><b>${escapeHtml(m.icon)}</b>${escapeHtml(m.title)}<small>${escapeHtml(m.description)}</small></button>`).join('');
}
function builderOpenMenu(id) {
  const m=builderDocument().menus.find(x=>x.id===id&&x.active);if(!m)return;
  closeModal();
  if(m.destination==='submenu') {
    const parent=builderDocument().menus.find(x=>x.id===m.parent_id);
    modal(m.title,`${parent?`<button class="text-button" data-builder-action="menu" data-builder-id="${escapeHtml(parent.id)}">← ${escapeHtml(parent.title)}</button>`:''}<div class="quick-grid">${builderMenuTiles(m.id)||'<p class="helper">Nothing has been added here yet.</p>'}</div>`);
  } else if(m.destination==='note') modal(m.title,`<p>${escapeHtml(m.content).replace(/\n/g,'<br>')}</p>`);
  else if(m.destination==='layout') void builderOpenLayout(m.layout_id);
  else if(m.destination==='profile') {state.tab='builder-profile';render();}
  else {state.tab=m.destination;render();}
}
async function builderOpenLayout(id,archived=false) {
  builderRuntime.layout=builderDocument().layouts.find(x=>x.id===id);
  if(!builderRuntime.layout){toast('This database is no longer available. Refresh Align.');return;}
  builderRuntime.archived=archived;builderRuntime.search='';builderRuntime.loading=true;builderRuntime.error='';
  state.tab='builder-records';render();
  try {const data=await api(`/api/builder/records/${id}?archived=${archived?1:0}`);builderRuntime.records=data.records;}
  catch(err){builderRuntime.records=[];builderRuntime.error=err.message;}
  finally{builderRuntime.loading=false;if(state.tab==='builder-records')render();}
}
function builderRecordActions(row) {
  const e=escapeHtml;
  return `<div class="builder-actions">${builderRuntime.archived?`<button class="small-button" data-builder-action="restore" data-builder-id="${e(row.id)}">Restore</button>`:`<button class="small-button" data-builder-action="edit" data-builder-id="${e(row.id)}">Edit</button><button class="small-button" data-builder-action="delete" data-builder-id="${e(row.id)}">Delete</button>`}</div>`;
}
function builderFieldText(field, value) {
  const raw = AlignFields.display(value);
  if (field?.type === 'date' && raw) return formatDisplayDate(raw) || raw;
  return raw;
}
function builderRecordList() {
  const {layout,records,search}=builderRuntime,e=escapeHtml;
  if(builderRuntime.loading)return '<p class="builder-empty">Loading records…</p>';
  if(builderRuntime.error)return `<p class="builder-empty">${e(builderRuntime.error)}</p>`;
  const shown=records.filter(r=>layout.fields.some(f=>(builderFieldText(f, r.values[f.id]) + ' ' + AlignFields.display(r.values[f.id])).toLowerCase().includes(search.toLowerCase())));
  if(!shown.length)return '<p class="builder-empty">No records here yet.</p>';
  if(layout.finance)return AlignFinance.summary(shown,builderRecordActions);
  const totals='<div class="card"><strong>Totals for '+shown.length+' shown records</strong>'+layout.fields.filter(f=>['number','formula'].includes(f.type)).map(f=>'<p>'+e(f.label)+': '+(shown.reduce((sum,r)=>sum+Math.round(Number(r.values[f.id]||0)*100),0)/100).toFixed(2)+'</p>').join('')+shown.filter(r=>r.calculation_error).map(r=>'<p role="alert">'+e(r.calculation_error)+' — edit the record to fill in missing values. Incomplete amounts are excluded from totals.</p>').join('')+'</div>';
  if(layout.view==='cards')return totals+ `<div class="builder-record-cards">${shown.map(r=>`<article class="card"><dl>${layout.fields.map(f=>`<dt>${e(f.label)}</dt><dd>${e(builderFieldText(f, r.values[f.id]))||'—'}</dd>`).join('')}</dl><div style="margin-top:18px">${builderRecordActions(r)}</div></article>`).join('')}</div>`;
  return totals+`<div class="builder-table-wrap"><table class="builder-table"><thead><tr>${layout.fields.map(f=>`<th scope="col">${e(f.label)}</th>`).join('')}<th scope="col">Actions</th></tr></thead><tbody>${shown.map(r=>`<tr>${layout.fields.map(f=>`<td>${e(builderFieldText(f, r.values[f.id]))||'—'}</td>`).join('')}<td>${builderRecordActions(r)}</td></tr>`).join('')}</tbody></table></div>`;
}
function builderRecordsPage() {
  const layout=builderRuntime.layout;if(!layout)return '<p>Choose a database from Home.</p>';
  return `<section class="page builder-record-page"><button class="text-button builder-back" data-builder-action="home">← Home</button><div class="hero"><p class="eyebrow">Your records${builderRuntime.archived?' · Deleted':''}</p><h1>${escapeHtml(layout.title)}</h1><p class="subtle">${escapeHtml(layout.description)}</p></div><div class="builder-record-toolbar"><input type="search" aria-label="Search records" placeholder="Search records…" data-builder-search value="${escapeHtml(builderRuntime.search)}">${!builderRuntime.archived?'<button class="primary-button" data-builder-action="new">Add record</button>':''}<button class="secondary-button" data-builder-action="toggle-deleted">${builderRuntime.archived?'Active records':'Deleted records'}</button><button class="secondary-button" data-builder-action="export-records">Export CSV</button></div><div data-builder-list>${builderRecordList()}</div><p class="helper">Records are private to your account. Connect to Align to add or edit records.</p></section>`;
}
function builderEditRecord(id) {
  const row=builderRuntime.records.find(x=>x.id===id);
  const fields=builderRuntime.layout.fields.map(f=>f.allow_custom?{...f,options:[...new Set([...f.options,...builderRuntime.records.map(r=>r.values[f.id]).filter(Boolean)])]}:f);
  modal(row?'Edit record':'Add record',`<form class="settings-form" data-builder-form="record" data-record-id="${escapeHtml(row?.id||'record_'+crypto.randomUUID().replace(/-/g,''))}" data-record-existing="${row?'1':'0'}" data-record-revision="${row?.revision||0}"><div data-record-fields>${AlignFields.render(fields,row?.values||{},'record')}</div><div data-record-review hidden></div><p class="helper" role="status" data-builder-error></p><div class="modal-actions"><button type="button" class="secondary-button" data-action="close-modal">Cancel</button><button type="button" class="secondary-button" data-builder-action="back-to-form" hidden>Back to edit</button><button class="primary-button">${builderRuntime.layout.review_before_save?'Review summary':'Save record'}</button></div></form>`);
}
document.addEventListener('input',ev=>{if(ev.target.hasAttribute('data-builder-search')){builderRuntime.search=ev.target.value;document.querySelector('[data-builder-list]').innerHTML=builderRecordList();}});
document.addEventListener('click',async ev=>{
  const button=ev.target.closest('[data-builder-action]');if(!button)return;
  const action=button.dataset.builderAction,id=button.dataset.builderId;
  try {
    if(action==='back-to-form'){
      const form=button.closest('form');delete form.dataset.reviewed;
      form.querySelector('[data-record-fields]').hidden=false;form.querySelector('[data-record-review]').hidden=true;
      form.querySelector('.primary-button').textContent='Review summary';button.hidden=true;return;
    }
    if(action==='menu')builderOpenMenu(id);
    if(action==='home'){state.tab='home';render();}
    if(action==='new')builderEditRecord();
    if(action==='edit')builderEditRecord(id);
    if(action==='toggle-deleted')await builderOpenLayout(builderRuntime.layout.id,!builderRuntime.archived);
    if(action==='delete'||action==='restore'){
      if(action==='delete'&&!confirm('Move this record to Deleted records? You can restore it later.'))return;
      const row=builderRuntime.records.find(x=>x.id===id);button.disabled=true;
      await api(`/api/builder/records/${builderRuntime.layout.id}/${id}`,{method:'DELETE',body:{revision:row.revision,restore:action==='restore'}});
      await builderOpenLayout(builderRuntime.layout.id,builderRuntime.archived);toast(action==='restore'?'Record restored.':'Record moved to Deleted records.');
    }
    if(action==='export-records'){
      const cols=builderRuntime.layout.fields;
      const quote=(field,value)=>{let text=field?builderFieldText(field,value):AlignFields.display(value);if(/^[=+@\-\t\r]/.test(text))text="'"+text;return '"'+text.replace(/"/g,'""')+'"';};
      const csv=[cols.map(f=>quote(null,f.label)).join(','),...builderRuntime.records.map(r=>cols.map(f=>quote(f,r.values[f.id])).join(','))].join('\r\n');
      const url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='align-records.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
  }catch(err){toast(err.message);button.disabled=false;}
});
document.addEventListener('submit',async ev=>{
  const form=ev.target;if(!form.matches('[data-builder-form]'))return;
  ev.preventDefault();ev.stopImmediatePropagation();const submit=form.querySelector('button.primary-button');submit.disabled=true;
  try {
    if(form.dataset.builderForm==='profile'){
      const values=AlignFields.values(form,builderDocument().startup.fields);
      await api('/api/personal/preferences',{method:'PUT',body:travelValues(form)});
      await api('/api/builder/profile',{method:'PUT',body:{values}});state.tab='home';await refresh();toast('Personal details saved.');
    }else{
      const lid=builderRuntime.layout.id,rid=form.dataset.recordId;
      if(builderRuntime.layout.review_before_save&&!form.dataset.reviewed){
        const data=await api(`/api/builder/records/${lid}/preview`,{method:'POST',body:{values:AlignFields.values(form,builderRuntime.layout.fields)}});
        const values=data.values,e=escapeHtml;
        form.querySelector('[data-record-review]').innerHTML='<h3>Summary / Confirm</h3><dl>'+builderRuntime.layout.fields.filter(f=>AlignFields.visible(f,values)).map(f=>`<dt>${e(f.label)}</dt><dd>${e(builderFieldText(f, values[f.id]))||'—'}</dd>`).join('')+'</dl>'+(builderRuntime.layout.finance?AlignFinance.review(values):'');
        form.querySelector('[data-record-fields]').hidden=true;form.querySelector('[data-record-review]').hidden=false;
        form.querySelector('[data-builder-action="back-to-form"]').hidden=false;form.querySelector('[data-builder-error]').textContent='';
        form.dataset.reviewed='1';submit.textContent='Confirm and save';submit.disabled=false;return;
      }
      await api(`/api/builder/records/${lid}${form.dataset.recordExisting==='1'?'/'+rid:''}`,{method:form.dataset.recordExisting==='1'?'PUT':'POST',body:{id:rid,revision:Number(form.dataset.recordRevision),values:AlignFields.values(form,builderRuntime.layout.fields)}});
      closeModal();await builderOpenLayout(lid);toast('Record saved.');
    }
  }catch(err){form.querySelector('[data-builder-error]').textContent=err.message;submit.disabled=false;}
},true);

from pathlib import Path
p=Path(__file__).resolve().parents[1]/'static'
h=(p/'owner-builder.html').read_text(encoding='utf-8')
h=h.replace('150-otp1','150-edit1').replace('<h1>App builder</h1>','<h1>Full edit mode</h1>').replace('Shape the first welcome, the menus, and the forms people use.','Find and edit forms, menus, layouts, and Home. Review your draft before publishing.')
h=h.replace('<button id="undo"','<button id="redo" class="secondary-button" disabled>Redo</button><button id="undo"')
h=h.replace('<button data-tab="startup"','<button data-tab="overview" aria-pressed="true">Edit overview</button><button data-tab="review" aria-pressed="false">Review changes</button><button data-tab="startup"')
h=h.replace('<div id="builder-content">','<div class="builder-tools"><label>Find anything <input id="edit-search" type="search" placeholder="Search menus, layouts, or fields"></label><label>Preview width <select id="preview-size"><option value="desktop">Desktop</option><option value="phone">Phone</option></select></label><span id="draft-indicator" role="status"></span></div><div id="builder-content">')
(p/'owner-builder.html').write_text(h,encoding='utf-8')
j=(p/'owner-builder.js').read_text(encoding='utf-8').replace("tab = 'startup'","tab = 'overview'").replace('history = [], dirty','history = [], future = [], dirty')
j=j.replace("function changed() { history.push", "function changed() { future=[]; history.push")
j=j.replace("$('#undo').disabled=busy||!history.length;", "$('#undo').disabled=busy||!history.length; $('#redo').disabled=busy||!future.length; $('#draft-indicator').textContent=dirty?'Unsaved edits':state?'Draft saved · Live revision '+state.published_revision:'';")
insert='''
  function editIndex() {
    return [
      {title:doc.startup.title,detail:'Welcome and personal details',tab:'startup'},
      ...doc.startup.fields.map(f=>({title:f.label,detail:'Startup field · '+types[f.type],tab:'startup',field:f.id})),
      ...doc.menus.map(m=>({title:m.title,detail:'Menu · '+destinations[m.destination],tab:'menus',item:m.id})),
      ...doc.layouts.flatMap(l=>[{title:l.title,detail:'Database layout · '+l.fields.length+' fields',tab:'layouts',item:l.id},...l.fields.map(f=>({title:f.label,detail:l.title+' · '+types[f.type],tab:'layouts',item:l.id,field:f.id}))]),
      {title:'Home and navigation',detail:'Labels, icons, visibility and order',tab:'home-nav'}
    ];
  }
  function overview() {
    const query=$('#edit-search').value.trim().toLowerCase();
    const items=editIndex().filter(x=>(x.title+' '+x.detail).toLowerCase().includes(query));
    return '<h2>Edit your app</h2><p class="helper">Select an item to open its full editor and live preview.</p>'+items.map(x=>`<button class="builder-jump" data-jump="${e(x.tab)}" data-select="${e(x.item||'')}" data-select-field="${e(x.field||'')}"><strong>${e(x.title)}</strong><small>${e(x.detail)}</small><span aria-hidden="true">→</span></button>`).join('')+(items.length?'':'<p>No matching items. Try a different name.</p>');
  }
  function differences(a,b,path='',out=[]) {
    if(JSON.stringify(a)===JSON.stringify(b))return out;
    if(a&&b&&typeof a==='object'&&typeof b==='object'&&!Array.isArray(a)&&!Array.isArray(b)) {
      for(const k of new Set([...Object.keys(a),...Object.keys(b)]))differences(a[k],b[k],path?path+' / '+k:k,out);
    } else if(Array.isArray(a)&&Array.isArray(b)&&[...a,...b].every(x=>x&&x.id)) {
      if(a.map(x=>x.id).join()!==b.map(x=>x.id).join())out.push({path:path+' / order',before:a.map(x=>x.title||x.label||x.id),after:b.map(x=>x.title||x.label||x.id)});
      for(const id of new Set([...a,...b].map(x=>x.id))) {
        const old=a.find(x=>x.id===id),next=b.find(x=>x.id===id);
        differences(old,next,path+' / '+(next?.title||next?.label||old?.title||old?.label||id),out);
      }
    } else out.push({path,before:a,after:b});
    return out;
  }
  function review() {
    const rows=differences(state.published,doc);
    const value=v=>v===undefined?'Not present':typeof v==='string'?v:JSON.stringify(v,null,2);
    return `<h2>Review changes</h2><p class="helper">Compare your current draft with published revision ${state.published_revision}. ${rows.length} changes. Saving a draft keeps it private; publishing applies it to the app.</p>`+rows.map(r=>`<article class="builder-change"><h3>${e(r.path)}</h3><div class="builder-two"><div><small>Published</small><pre>${e(value(r.before))}</pre></div><div><small>Draft</small><pre>${e(value(r.after))}</pre></div></div></article>`).join('')+(rows.length?'':'<p>Your draft matches the published configuration.</p>');
  }
'''
j=j.replace('  function render(previewOnly=false) {',insert+'  function render(previewOnly=false) {')
j=j.replace("if(tab==='startup') {", "if(tab==='overview') { editor=overview(); preview='<h2>Master editing</h2><p>Manage each part of Align through its dedicated editor.</p><p><a href=\"/admin\">Work and calendar settings</a></p><p><a href=\"/beta-admin\">Owner and account controls</a></p><p>Use Undo and Redo while editing. Export a configuration backup from the footer, or save your draft to continue later.</p>'; } else if(tab==='review') { editor=review(); preview='<h2>Ready to publish?</h2><p>Check the published and draft values, then use Publish changes above. Existing saved user records are retained.</p>'; } else if(tab==='startup') {")
j=j.replace("const el=ev.target,key=el.dataset.prop;", "const el=ev.target,key=el.dataset.prop||'';")
j=j.replace("doc.home_sections[Number(el.dataset.sectionIndex)].visible=el.checked", "doc.home_sections.slice().sort((a,b)=>a.sort_order-b.sort_order)[Number(el.dataset.sectionIndex)].visible=el.checked")
j=j.replace("if(b.dataset.tab){", "if(b.dataset.jump){tab=b.dataset.jump;selected=b.dataset.select||'';fieldId=b.dataset.selectField||'';render();return;}\n    if(b.dataset.tab){")
j=j.replace('dirty=false;history=[];', 'dirty=false;history=[];future=[];')
j=j.replace('doc=history.pop();dirty=true;', 'future.push(copy(doc));doc=history.pop();dirty=true;')
j=j.replace("  $('#save').onclick", "  $('#redo').onclick=()=>{if(busy||!future.length)return;history.push(copy(doc));doc=future.pop();dirty=true;fieldId='';render();status('Change restored.');};\n  $('#edit-search').oninput=()=>{tab='overview';render();};\n  $('#preview-size').onchange=ev=>document.body.classList.toggle('phone-preview',ev.target.value==='phone');\n  $('#save').onclick")
(p/'owner-builder.js').write_text(j,encoding='utf-8')
with (p/'owner-builder.css').open('a',encoding='utf-8') as f:
    f.write('''
.builder-tools{display:flex;align-items:end;gap:18px;flex-wrap:wrap;margin:20px 0}.builder-tools label{display:grid;gap:6px;font-size:14px}.builder-tools input,.builder-tools select{font:inherit;padding:12px;border:1px solid #ccd5e3;border-radius:9px;max-width:100%}.builder-tools label:first-child{flex:1;min-width:220px}.builder-jump{display:grid;grid-template-columns:1fr auto;width:100%;text-align:left;background:#f8faff;border:1px solid #dfe5ee;border-radius:12px;padding:16px;margin:9px 0;cursor:pointer;color:inherit;font:inherit;gap:5px}.builder-jump small{grid-column:1;color:#62708a}.builder-jump span{grid-column:2;grid-row:1/3;align-self:center}.builder-jump:hover{border-color:#365ce6;background:#eef3ff}.builder-change{border-top:1px solid #dfe5ee;padding:12px 0}.builder-change h3{overflow-wrap:anywhere}.builder-change pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;font-size:13px;background:#f5f7fb;padding:12px;border-radius:8px;max-height:260px;overflow:auto}.phone-preview #builder-content aside{width:100%;max-width:390px;justify-self:center;box-sizing:border-box}.builder-heading{position:sticky;top:0;background:#f5f7fb;z-index:3;padding:10px 0}.builder-heading .button-row{flex-wrap:wrap}.builder-tabs{flex-wrap:wrap}@media(max-width:850px){.builder-heading{position:static}.builder-tools{align-items:stretch}.builder-tabs{gap:4px}}
''')

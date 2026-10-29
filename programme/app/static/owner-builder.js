(() => {
  const e = AlignFields.escape, $ = s => document.querySelector(s);
let state, doc,
    tab = 'overview',
    selected = '',
    fieldId = '',
    workflowNodeId = '',
    financeView = 'setup',
    history = [],
    future = [],
    dirty = false,
    busy = false,
    lastRenderedTab = '';

const types = {
  text: 'Short text',
  textarea: 'Long text',
  tel: 'Phone number',
  email: 'Email',
  number: 'Number',
  formula: 'Calculated amount',
  date: 'Date',
  select: 'Dropdown',
  checkbox: 'Checkbox'
};

const destinations = {
  submenu: 'Folder / submenu',
  note: 'Information page',
  layout: 'List',
  profile: 'Personal details',
  add: 'Add shifts',
  calendar: 'Schedule',
  settings: 'Settings'
};
const id = prefix =>
  `${prefix}_${crypto.randomUUID().replace(/-/g,'')}`;

const copy = value =>
  JSON.parse(JSON.stringify(value));

async function api(path, options={}) {
  const r = await fetch(path, {
    ...options,
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...(sessionStorage.getItem('align-admin-token')
        ? {
            'X-Align-Admin':
              sessionStorage.getItem('align-admin-token')
          }
        : {})
    },
    body: options.body
      ? JSON.stringify(options.body)
      : undefined
  });

  const data = await r.json();

  if(!r.ok) {
    throw Error(
      data.error ||
      'Unable to complete this action.'
    );
  }

  return data;
}
  function inUnifiedDesign() { const pane=$('#design-pane'); return Boolean(pane&&!pane.hidden); }
  function status(message, error=false) { const saved=/^(Draft saved|Published)/.test(message); $('#builder-status').textContent=message; $('#builder-status').classList.toggle('builder-error',error); const shared=$('#management-status'); if(shared&&!inUnifiedDesign()) { shared.textContent=message; shared.dataset.state=error?'error':saved?'saved':''; } if(window.AlignStudioNotice&&(error||saved)) window.AlignStudioNotice(message, error?'error':'saved'); }
  function controls() { $('#draft-indicator').textContent=dirty?'Unsaved edits':state?'Draft saved · Live revision '+state.published_revision:''; if(inUnifiedDesign()) return; for(const name of ['save','publish']) $('#'+name).disabled=busy||!doc; $('#undo').disabled=busy||!history.length; $('#redo').disabled=busy||!future.length; $('#discard').disabled=busy||!doc; $('#export').disabled=!doc; $('#import').disabled=busy; }
  function changed() { future=[]; history.push(copy(doc)); if(history.length>50) history.shift(); dirty=true; }
  function currentLayout() { return doc.layouts.find(x=>x.id===selected); }
  function fields() { return tab==='startup'?doc.startup.fields:currentLayout()?.fields; }
  function input(label,key,value,type='text') {return `<div class="field"><label>${e(label)}<input data-prop="${key}" type="${type}" value="${e(value)}"></label></div>`;}
  function area(label,key,value) {return `<div class="field"><label>${e(label)}<textarea data-prop="${key}" rows="3">${e(value)}</textarea></label></div>`;}
  function options(items,value) {return Object.entries(items).map(([k,v])=>`<option value="${e(k)}" ${value===k?'selected':''}>${e(v)}</option>`).join('');}
  function fieldList() {
    const list=fields(); if(!list) return '';
    const field=list.find(f=>f.id===fieldId);
    const oldFields=tab==='startup'?state.published.startup.fields:state.published.layouts.find(l=>l.id===selected)?.fields||[];
    return `<h3>Form fields</h3><p class="helper">Move fields to change the form and column order. Removing a field hides it; previously saved values are retained.</p>${list.map((f,i)=>`<div class="builder-row ${f.id===fieldId?'selected':''}"><button class="builder-row-title" data-field="${e(f.id)}">${e(f.label)}<small>${e(types[f.type])}${f.required?' · Required':' · Optional'}</small></button><div class="builder-row-actions"><button data-move-field="${e(f.id)}" data-dir="-1" ${!i?'disabled':''} aria-label="Move ${e(f.label)} up">↑</button><button data-move-field="${e(f.id)}" data-dir="1" ${i===list.length-1?'disabled':''} aria-label="Move ${e(f.label)} down">↓</button><button data-remove-field="${e(f.id)}" ${tab==='startup'&&f.id==='user_name'?'disabled':''} aria-label="Delete ${e(f.label)}">×</button></div></div>`).join('')}<button class="secondary-button" data-add-field>Add field</button>${field?`<div class="builder-editor" data-field-editor><h3>Edit ${e(field.label)}</h3>${input('Field label','label',field.label)}<div class="field"><label>Field type<select data-prop="type" ${oldFields.some(f=>f.id===field.id)?'disabled':''}>${options(types,field.type)}</select></label></div>${oldFields.some(f=>f.id===field.id)?'<p class="helper">This field has been published. Add a new field to use a different type.</p>':''}${area('Help text','help',field.help)}${field.type==='formula'?area('Formula — e.g. [Amount] - [Paid]','formula',field.formula||'')+'<p class="helper">Use + − * / and parentheses. Available numeric fields: '+e(list.filter(f=>f.id!==field.id&&['number','formula'].includes(f.type)).map(f=>'['+f.label+']').join(', '))+'. Results calculate on save; blank inputs and division by zero show an error.</p>':''}${field.type==='select'?area('Choices (one per line)','options',field.options.join('\n')):''}<label><input type="checkbox" data-prop="required" ${field.required?'checked':''} ${tab==='startup'&&field.id==='user_name'?'disabled':''}> Required</label></div>`:''}`;
  }
  function databaseFlowNodes(layout) {
    return [{id:'__flow_start__', label:'Begin entry', kind:'start'}, ...(layout.fields || []).map(field => ({id:field.id, label:field.label || field.id, kind:'field', field})), {id:'__flow_finish__', label:'Review and save', kind:'finish'}];
  }
  function databaseFlowEdges(layout) {
    if (Array.isArray(layout.database_flow?.edges)) return layout.database_flow.edges;
    const nodes = databaseFlowNodes(layout);
    return nodes.slice(0, -1).map((node, index) => ({from:node.id, to:nodes[index + 1].id}));
  }
  function databaseFlowLabel(layout, nodeId) { return databaseFlowNodes(layout).find(node => node.id === nodeId)?.label || nodeId; }
  function databaseFlowOptions(layout, selectedId) { return databaseFlowNodes(layout).map(node => `<option value="${e(node.id)}" ${node.id === selectedId ? 'selected' : ''}>${e(node.label)}</option>`).join(''); }
  function databaseFlowSvg(layout) {
    const nodes = databaseFlowNodes(layout), edges = databaseFlowEdges(layout);
    const columns = Math.min(3, Math.max(1, Math.ceil(Math.sqrt(nodes.length))));
    const cellWidth = 260, cellHeight = 165, nodeWidth = 190, nodeHeight = 72;
    const positions = new Map(nodes.map((node,index) => [node.id, {x:30+(index%columns)*cellWidth, y:30+Math.floor(index/columns)*cellHeight, row:Math.floor(index/columns)}]));
    const rows = Math.ceil(nodes.length / columns), width = columns * cellWidth + 30, height = rows * cellHeight + 30;
    const paths = edges.map(edge => {
      const source = positions.get(edge.from), target = positions.get(edge.to); if (!source || !target) return '';
      let sx, sy, tx, ty, d;
      if (target.row > source.row) { sx=source.x+nodeWidth/2; sy=source.y+nodeHeight; tx=target.x+nodeWidth/2; ty=target.y; const mid=(sy+ty)/2; d=`M ${sx} ${sy} C ${sx} ${mid}, ${tx} ${mid}, ${tx} ${ty}`; }
      else if (target.row < source.row) { sx=source.x+nodeWidth/2; sy=source.y; tx=target.x+nodeWidth/2; ty=target.y+nodeHeight; const mid=(sy+ty)/2; d=`M ${sx} ${sy} C ${sx} ${mid}, ${tx} ${mid}, ${tx} ${ty}`; }
      else if (target.x > source.x) { sx=source.x+nodeWidth; sy=source.y+nodeHeight/2; tx=target.x; ty=target.y+nodeHeight/2; const mid=(sx+tx)/2; d=`M ${sx} ${sy} C ${mid} ${sy}, ${mid} ${ty}, ${tx} ${ty}`; }
      else { sx=source.x; sy=source.y+nodeHeight/2; tx=target.x+nodeWidth; ty=target.y+nodeHeight/2; const mid=(sx+tx)/2; d=`M ${sx} ${sy} C ${mid} ${sy}, ${mid} ${ty}, ${tx} ${ty}`; }
      return `<path class="database-flow-svg-edge" d="${d}" marker-end="url(#database-flow-arrow)"/>`;
    }).join('');
    const cards = nodes.map(node => {
      const p=positions.get(node.id), field=node.field, kind=node.kind;
      const type=kind==='field' ? (types[field.type]||field.type) : (kind==='start'?'START':'FINISH');
      const label=(node.label||node.id).length>24 ? (node.label||node.id).slice(0,21)+'…' : (node.label||node.id);
      const detail=kind==='field' ? (field.required?'Required':'Optional')+' · '+type : (kind==='start'?'Open the form':layout.review_before_save===false?'Save after validation':'Review answers before saving');
      const isSelected = fieldId === node.id;
      const actionLabel = kind === 'field' ? `Edit field: ${node.label}` : kind === 'start' ? 'Select beginning of entry flow' : 'Select end of entry flow';
      return `<g class="database-flow-svg-card database-flow-svg-${kind} ${isSelected ? 'is-selected' : ''}" role="button" tabindex="0" aria-label="${e(actionLabel)}" aria-pressed="${isSelected ? 'true' : 'false'}" data-database-flow-node="${e(node.id)}" data-database-flow-kind="${kind}"><rect x="${p.x}" y="${p.y}" width="${nodeWidth}" height="${nodeHeight}" rx="12"/><text class="database-flow-svg-type" x="${p.x+12}" y="${p.y+20}">${e(type.toUpperCase())}</text><text class="database-flow-svg-label" x="${p.x+12}" y="${p.y+42}">${e(label)}</text><text class="database-flow-svg-detail" x="${p.x+12}" y="${p.y+59}">${e(detail)}</text></g>`;
    }).join('');
    return `<div class="database-flow-svg-wrap"><svg class="database-flow-svg" role="img" aria-label="Database flowchart with ${nodes.length} nodes and ${edges.length} connections" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}"><defs><marker id="database-flow-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z"/></marker></defs>${paths}${cards}</svg></div>`;
  }

  function previewFields(list) {return `<form class="settings-form" data-preview-form>${AlignFields.render(list,{},'preview')}</form>`;}
  document.addEventListener('submit', event => {
    if (event.target && event.target.matches && event.target.matches('[data-preview-form]')) event.preventDefault();
  }, true);
  function workflowNodeLabel(layout,node) {
  if(['field','choice'].includes(node.type)) {
    const field=layout.fields.find(f=>f.id===node.field_id);
    return field?.label || node.field_id;
  }

  if(node.type==='calculation') return 'Calculate finance values';
  if(node.type==='summary') return node.title || 'Summary / Confirm';
  if(node.type==='save') return 'Save record';
  if(node.type==='destination') return 'Finance summary';

  return node.id;
}

function workflowCondition(edge,layout) {
  if(!edge.when) return '';

  const field=layout.fields.find(f=>f.id===edge.when.field);
  const label=field?.label || edge.when.field;

  let value=edge.when.equals;

  if(value===true) value='Yes';
  if(value===false) value='No';

  return `${label}: ${value}`;
}
function workflowConditionFields(layout) {
  return layout.fields.filter(field =>
    ['select','checkbox'].includes(field.type)
  );
}

function workflowConditionChoices(field) {
  if(!field) return [];

  if(field.type==='checkbox') {
    return [
      {value:false,label:'No'},
      {value:true,label:'Yes'}
    ];
  }

  return (field.options||[]).map(value=>({
    value,
    label:value
  }));
}

function workflowConditionEditor(layout,edge,index) {
  if(!edge.when) {
    return `
      <div class="workflow-condition-editor">
        <strong>From ${e(edge.from)}</strong>
        <p class="helper">Always follows this connection.</p>
      </div>
    `;
  }

  const fields=workflowConditionFields(layout);
  const selectedField=layout.fields.find(
    field=>field.id===edge.when.field
  );

  const choices=workflowConditionChoices(selectedField);

  return `
    <div class="workflow-condition-editor">
      <strong>From ${e(edge.from)}</strong>

      <div class="builder-two">
        <div class="field">
          <label>
            Condition field
            <select data-workflow-condition-field="${index}">
              ${fields.map(field=>`
                <option
                  value="${e(field.id)}"
                  ${field.id===edge.when.field?'selected':''}
                >
                  ${e(field.label)}
                </option>
              `).join('')}
            </select>
          </label>
        </div>

        <div class="field">
          <label>
            Equals
            <select data-workflow-condition-value="${index}">
              ${choices.map(choice=>`
                <option
                  value="${e(JSON.stringify(choice.value))}"
                  ${JSON.stringify(choice.value)===JSON.stringify(edge.when.equals)?'selected':''}
                >
                  ${e(choice.label)}
                </option>
              `).join('')}
            </select>
          </label>
        </div>
      </div>
    </div>
  `;
}
function workflowNodeDetails(layout) {
  const workflow=layout?.workflow;

  if(!workflow?.nodes?.length) return '';

  if(!workflowNodeId) {
    return `
      <div class="builder-editor workflow-node-editor">
        <h3>Workflow node</h3>
        <p class="helper">Select a node in the workflow tree to inspect it.</p>
      </div>
    `;
  }

  const node=workflow.nodes.find(x=>x.id===workflowNodeId);

  if(!node) {
    workflowNodeId='';
    return `
      <div class="builder-editor workflow-node-editor">
        <h3>Workflow node</h3>
        <p class="helper">Select a node in the workflow tree to inspect it.</p>
      </div>
    `;
  }

  const field=['field','choice'].includes(node.type)
    ? layout.fields.find(f=>f.id===node.field_id)
    : null;

  const incoming=(workflow.edges||[]).filter(edge=>edge.to===node.id);
  const outgoing=(workflow.edges||[]).filter(edge=>edge.from===node.id);

  const edgeText=edge=>{
    const other=edge.from===node.id ? edge.to : edge.from;
    const condition=edge.when
      ? ` · ${workflowCondition(edge,layout)}`
      : '';

    return `${other}${condition}`;
  };

  let specific='';

  if(field) {
    specific=`
      <dt>Field</dt>
      <dd>${e(field.label)}</dd>

      <dt>Field ID</dt>
      <dd><code>${e(field.id)}</code></dd>

      <dt>Field type</dt>
      <dd>${e(field.type)}</dd>

      <dt>Required</dt>
      <dd>${field.required?'Yes':'No'}</dd>
    `;
  }

  if(node.type==='calculation') {
    specific=`
      <dt>Operation</dt>
      <dd><code>${e(node.operation||'')}</code></dd>

      <dt>Inputs</dt>
      <dd>${e((node.inputs||[]).join(', ')||'None')}</dd>

      <dt>Outputs</dt>
      <dd>${e((node.outputs||[]).join(', ')||'None')}</dd>
    `;
  }

  if(node.type==='summary') {
    specific=`
      <dt>Title</dt>
      <dd>${e(node.title||'Summary / Confirm')}</dd>

      <dt>Visible fields</dt>
      <dd>${e(node.visible_fields||'current_branch')}</dd>
    `;
  }

  if(node.type==='save') {
    specific=`
      <dt>Record type</dt>
      <dd>${e(node.record_type||'record')}</dd>
    `;
  }

  if(node.type==='destination') {
    specific=`
      <dt>Destination</dt>
      <dd>${e(node.screen||'')}</dd>
    `;
  }

  return `
    <div class="builder-editor workflow-node-editor">
      <p class="eyebrow">Selected workflow node</p>
      <h3>${e(workflowNodeLabel(layout,node))}</h3>

      <dl class="workflow-node-details">
        <dt>Node ID</dt>
        <dd><code>${e(node.id)}</code></dd>

        <dt>Type</dt>
        <dd>${e(node.type)}</dd>

        ${specific}
      </dl>

      <h4>Comes from</h4>

    ${
      incoming.length
        ? incoming.map(edge=>
            workflowConditionEditor(
              layout,
              edge,
              workflow.edges.indexOf(edge)
            )
          ).join('')
        : '<p class="helper">This is the workflow start node.</p>'
    }

      ${
        outgoing.length
          ? `<ul class="workflow-connection-list">${outgoing.map(edge=>`<li>${e(edgeText(edge))}</li>`).join('')}</ul>`
          : '<p class="helper">No following node.</p>'
      }

      <p class="helper">
         Existing branch conditions can be edited here.
         Adding, deleting and moving connections comes later.
        </p>
    </div>
  `;
}
function workflowTree(layout) {
  const workflow=layout.workflow;

  if(!workflow?.nodes?.length) {
    return '<p class="helper">No workflow has been configured for this layout.</p>';
  }

  const nodes=new Map(workflow.nodes.map(node=>[node.id,node]));
  const edges=new Map();

  for(const edge of workflow.edges||[]) {
    if(!edges.has(edge.from)) edges.set(edge.from,[]);
    edges.get(edge.from).push(edge);
  }

  function branch(nodeId,path=new Set()) {
    const node=nodes.get(nodeId);

    if(!node) return '';

    if(path.has(nodeId)) {
      return '<div class="workflow-cycle">↻ Workflow loop</div>';
    }

    const nextPath=new Set(path);
    nextPath.add(nodeId);

    const children=edges.get(nodeId)||[];

    return `
      <button
          type="button"
          class="workflow-node workflow-node-${e(node.type)} ${workflowNodeId===node.id?'is-selected':''}"
          data-workflow-node="${e(node.id)}"
          aria-pressed="${workflowNodeId===node.id?'true':'false'}"
        >
          <small>${e(node.type)}</small>
          <strong>${e(workflowNodeLabel(layout,node))}</strong>
      </button>

        ${children.length ? `
          <div class="workflow-children">
            ${children.map(edge=>`
              <div class="workflow-child">
                <div class="workflow-arrow">↓</div>
                ${edge.when
                  ? `<div class="workflow-condition">${e(workflowCondition(edge,layout))}</div>`
                  : ''
                }
                ${branch(edge.to,nextPath)}
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `;
  }

  return `
    <div class="workflow-tree">
      ${branch(workflow.start_node)}
    </div>
  `;
}
  function menuTree(parent='',depth=0) {
    return doc.menus.filter(m=>m.parent_id===parent).map((m,i,siblings)=>`<div style="margin-left:${Math.min(depth,8)*16}px"><div class="builder-row ${selected===m.id?'selected':''}"><button class="builder-row-title" data-item="${e(m.id)}">${e(m.icon)} ${e(m.title)}<small>${depth?'Secondary menu':'Primary menu'} · ${e(destinations[m.destination])}${m.active?'':' · Hidden'}</small></button><div class="builder-row-actions"><button data-move="${e(m.id)}" data-dir="-1" ${!i?'disabled':''} aria-label="Move ${e(m.title)} up">↑</button><button data-move="${e(m.id)}" data-dir="1" ${i===siblings.length-1?'disabled':''} aria-label="Move ${e(m.title)} down">↓</button></div></div>${menuTree(m.id,depth+1)}</div>`).join('');
  }
  function descendant(mid, ancestor) {let m=doc.menus.find(x=>x.id===mid);const seen=new Set();while(m?.parent_id&&!seen.has(m.id)){seen.add(m.id);if(m.parent_id===ancestor)return true;m=doc.menus.find(x=>x.id===m.parent_id);}return false;}
  function menuEditor() {
    const m=doc.menus.find(x=>x.id===selected); if(!m)return '<p class="helper">Select a menu item to edit its title, destination, and parent.</p>';
    return `<div class="builder-editor" data-menu-editor><h3>Edit menu item</h3>${input('Title','title',m.title)}${area('Description','description',m.description)}<div class="builder-two">${input('Icon or emoji','icon',m.icon)}${input('Colour','colour',m.colour,'color')}</div><div class="field"><label>Menu location<select data-prop="parent_id"><option value="">Home (primary menu)</option>${doc.menus.filter(x=>x.destination==='submenu'&&x.id!==m.id&&!descendant(x.id,m.id)).map(x=>`<option value="${e(x.id)}" ${m.parent_id===x.id?'selected':''}>Inside ${e(x.title)}</option>`).join('')}</select></label></div><div class="field"><label>Opens<select data-prop="destination">${options(destinations,m.destination)}</select></label></div>${m.destination==='layout'?`<div class="field"><label>Database layout<select data-prop="layout_id"><option value="">Choose a layout</option>${doc.layouts.map(x=>`<option value="${e(x.id)}" ${m.layout_id===x.id?'selected':''}>${e(x.title)}</option>`).join('')}</select></label></div>`:''}${m.destination==='note'?area('Page content','content',m.content):''}<label><input type="checkbox" data-prop="active" ${m.active?'checked':''}> Visible to users</label><div class="button-row" style="margin-top:18px"><button class="secondary-button" data-add-child ${m.destination!=='submenu'?'disabled':''}>Add secondary item</button><button class="danger-button" data-delete-menu>Delete menu item</button></div></div>`;
  }
  function menuPreview(parent='',depth=0) {return doc.menus.filter(x=>x.parent_id===parent&&x.active).map(m=>`<div style="margin-left:${Math.min(depth,8)*12}px"><article class="card" style="padding:14px;border-left:4px solid ${e(m.colour)}"><strong>${e(m.icon)} ${e(m.title)}</strong><p class="helper">${e(m.description||destinations[m.destination])}</p></article>${menuPreview(m.id,depth+1)}</div>`).join('');}
  function homeNavigationEditor(embedded=false) {
    const nav=doc.navigation||[], sections=(doc.home_sections||[]).slice().sort((a,b)=>a.sort_order-b.sort_order);
    const move=(attr,i,last)=>`<span class="studio-line-move"><button ${attr}="${i}" data-dir="-1" ${!i?'disabled':''} aria-label="Move up">↑</button><button ${attr}="${i}" data-dir="1" ${i===last?'disabled':''} aria-label="Move down">↓</button></span>`;
    const destinations=[['today','Today'],['inbox','Inbox'],['planner','Planner / Calendar'],['sections','Sections'],['more','More'],['add','Add shifts'],['settings','Settings'],['profile','Profile'],['note','Information page'],['layout','List']];
    const buttons=nav.map((n,i)=>`<div class="studio-line"><input class="studio-line-icon" data-prop="nav-icon-${i}" value="${e(n.icon)}" aria-label="Icon"><input class="studio-line-name" data-prop="nav-title-${i}" value="${e(n.title)}" aria-label="Name"><select data-prop="nav-destination-${i}" aria-label="Button destination">${destinations.map(([value,label])=>`<option value="${value}" ${(n.destination||'today')===value?'selected':''}>${label}</option>`).join('')}</select><label class="studio-line-check"><input type="checkbox" data-nav-prop="active" data-nav-index="${i}" ${n.active?'checked':''}> Show</label>${move('data-nav-move',i,nav.length-1)}</div>`).join('');
    const blocks=sections.map((s,i)=>`<div class="studio-line is-section"><input class="studio-line-name" data-prop="section-title-${i}" value="${e(s.title)}" aria-label="Section name"><label class="studio-line-check"><input type="checkbox" data-section-prop="visible" data-section-index="${i}" ${s.visible?'checked':''}> Show</label>${move('data-section-move',i,sections.length-1)}<button type="button" class="secondary-button" data-remove-home-section="${e(s.id)}" aria-label="Remove ${e(s.title)} from home">Remove</button></div>`).join('');
    const available=[['today','Today at a glance'],['stats','Week summary'],['menus','Your sections'],['upcoming','Upcoming Events'],['calendar','Calendar'],['annual_leave','Annual leave']].filter(([id])=>!sections.some(s=>s.id===id));
    const head=embedded?'':`<h2>Home screen</h2><p class="helper">Add, remove, rename, show, hide, and reorder sections on your home screen. Changes stay in your draft until you publish.</p>`;
    return `${head}<h3>Bottom buttons</h3><div class="studio-lines">${buttons}</div><h3>Home sections</h3><div class="studio-lines">${blocks||'<p class="helper">No home sections yet. Add one below.</p>'}</div><div class="builder-option-group"><label>Add a section<select id="add-home-section"><option value="">Choose a section…</option>${available.map(([id,title])=>`<option value="${id}">${title}</option>`).join('')}</select></label><button type="button" class="secondary-button" data-add-home-section ${!available.length?'disabled':''}>Add section</button></div>`;
  }
  function baseStructureEditor() {
    const weather=doc.base_structure?.weather||{enabled:true,refresh_minutes:15,show_last_updated:true,show_errors:true,views:['today','hourly','daily']};
    return `<h2>Shared details</h2><p class="helper">Set the shared home screen, buttons, and weather. People’s saved records stay as they are.</p><div class="builder-banner">Version ${e(String(doc.base_structure?.version||1))}. Save a draft, then publish when you want people to see it.</div><h3>Navigation and Home</h3>${homeNavigationEditor(true)}<h3>Weather display defaults</h3><div class="builder-option-group"><label><input type="checkbox" data-base-weather="enabled" ${weather.enabled!==false?'checked':''}> Show weather on supported screens</label><label>Refresh interval<select data-base-weather="refresh_minutes">${options({5:'5 minutes',10:'10 minutes',15:'15 minutes',30:'30 minutes',60:'60 minutes'},String(weather.refresh_minutes||15))}</select></label><label><input type="checkbox" data-base-weather="show_last_updated" ${weather.show_last_updated!==false?'checked':''}> Show last-updated time</label><label><input type="checkbox" data-base-weather="show_errors" ${weather.show_errors!==false?'checked':''}> Show weather refresh errors</label></div><p class="helper">Weather views remain Today, Hourly, and Daily. Provider credentials and location privacy are not configurable here.</p><button type="button" class="secondary-button" data-reset-base>Reset base structure defaults</button>`;
  }
  function travelResultsEditor() {
    const t=doc.travel_results||{}, v=t.visibility||{};
    return `<h2>Travel</h2><p class="helper">Choose what a journey card shows. Saved journeys stay as they are.</p><div class="builder-option-group"><label><input type="checkbox" data-travel-prop="show_best_only" ${t.show_best_only!==false?'checked':''}> Show only the best journey first</label><label><input type="checkbox" data-travel-prop="show_more" ${t.show_more!==false?'checked':''}> Show a Show more / Show less alternatives control</label></div><h3>Journey information</h3><div class="builder-option-group">${[['leave_by','Leave-by time'],['departure_arrival','Departure and arrival'],['duration','Duration and walking'],['mode_provider','Mode and provider'],['weather_adjustment','Weather adjustment'],['traffic_adjustment','Traffic adjustment'],['actions','Journey actions']].map(([key,label])=>`<label><input type="checkbox" data-travel-visibility="${key}" ${v[key]!==false?'checked':''}> ${label}</label>`).join('')}</div><button type="button" class="secondary-button" data-reset-travel>Reset travel display defaults</button>`;
  }

  function editIndex() {
    return [
      {title:doc.startup.title,detail:'The first screen people see',tab:'startup'},
      ...doc.startup.fields.map(f=>({title:f.label,detail:'Welcome question · '+types[f.type],tab:'startup',field:f.id})),
      ...doc.menus.map(m=>({title:m.title,detail:'Menu item',tab:'menus',item:m.id})),
      ...doc.layouts.flatMap(l=>[{title:l.title,detail:'List · '+l.fields.length+' questions',tab:'layouts',item:l.id},...l.fields.map(f=>({title:f.label,detail:l.title+' · '+types[f.type],tab:'layouts',item:l.id,field:f.id}))]),
      {title:'Home screen and buttons',detail:'Names, icons, and what is shown',tab:'home-nav'}
    ];
  }
  function overview() {
    const query=($('#edit-search')?.value||'').trim().toLowerCase();
    const items=editIndex().filter(x=>(x.title+' '+x.detail).toLowerCase().includes(query));
    if(!query) return '';
    const shown=items;
    const groups=[['Welcome','startup'],['Menus','menus'],['Sections','layouts'],['Home screen','home-nav']];
    const jump=x=>`<button class="builder-jump" data-jump="${e(x.tab)}" data-select="${e(x.item||'')}" data-select-field="${e(x.field||'')}"><strong>${e(x.title)}</strong><small>${e(x.detail)}</small></button>`;
    const body=groups.map(([label,name])=>{
      const rows=shown.filter(x=>x.tab===name);
      return rows.length?`<h3 class="studio-index-label">${e(label)}</h3>${rows.map(jump).join('')}`:'';
    }).join('');
    return body||'<div class="studio-empty"><strong>Nothing matches</strong><p>Try a different word, or choose a section on the left.</p></div>';
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
    return `<h2>Check what will change</h2><p class="helper">This draft compared with the live app (version ${state.published_revision}). ${rows.length} ${rows.length===1?'change':'changes'}. Save draft keeps this private. Publish updates the app people use.</p>`+rows.map(r=>`<article class="builder-change"><h3>${e(r.path)}</h3><div class="builder-two"><div><small>Live now</small><pre>${e(value(r.before))}</pre></div><div><small>Your draft</small><pre>${e(value(r.after))}</pre></div></div></article>`).join('')+(rows.length?'':'<div class="studio-empty"><strong>Nothing new to publish</strong><p>This draft matches the live app.</p></div>');
  }

function financeNav() {
  return `
    <div class="finance-builder-tabs">
      ${[
        ['setup', 'Setup'],
        ['fields', 'Fields'],
        ['flow', 'Flow'],
        ['preview', 'Preview']
      ].map(([key, label]) => `
        <button
          type="button"
          data-finance-view="${key}"
          class="${financeView === key ? 'is-active' : ''}"
        >
          ${label}
        </button>
      `).join('')}
    </div>
  `;
}


function workflowFriendlyType(node) {
  if (node.type === 'choice') return 'Choice';
  if (node.type === 'field') return 'Question';
  if (node.type === 'calculation') return 'Automatic calculation';
  if (node.type === 'summary') return 'Review';
  if (node.type === 'save') return 'Save';
  if (node.type === 'destination') return 'Finish';

  return 'Step';
}


function workflowNodeMenu(layout) {
  const workflow = layout?.workflow;

  if (!workflow?.nodes?.length) {
    return `
      <aside class="finance-workflow-menu">
        <h3>Finance steps</h3>
        <p class="helper">
          No workflow steps are configured yet.
        </p>
      </aside>
    `;
  }

  return `
    <aside class="finance-workflow-menu">

      <p class="eyebrow">Finance flow</p>
      <h3>Steps</h3>

      <p class="helper">
        Pick a step to edit what happens there.
      </p>

      <div class="finance-workflow-step-list">

        ${workflow.nodes.map((node, index) => `
          <button
            type="button"
            class="
              finance-workflow-step
              ${workflowNodeId === node.id ? 'is-selected' : ''}
            "
            data-workflow-node="${e(node.id)}"
          >

            <span class="finance-workflow-number">
              ${index + 1}
            </span>

            <span class="finance-workflow-step-text">
              <strong>
                ${e(workflowNodeLabel(layout, node))}
              </strong>

              <small>
                ${e(workflowFriendlyType(node))}
              </small>
            </span>

            <span
              class="finance-workflow-arrow"
              aria-hidden="true"
            >
              ›
            </span>

          </button>
        `).join('')}

      </div>

    </aside>
  `;
}


function friendlyWorkflowConditionEditor(layout, edge, index) {
  if (!edge.when) {
    return `
      <div class="finance-rule">
        <p class="helper">
          This step always follows the previous step.
        </p>
      </div>
    `;
  }

  const conditionFields = workflowConditionFields(layout);

  const selectedField = layout.fields.find(
    field => field.id === edge.when.field
  );

  const choices = workflowConditionChoices(selectedField);

  return `
    <div class="finance-rule">

      <div class="finance-rule-grid">

        <label>
          Show when

          <select
            data-workflow-condition-field="${index}"
          >
            ${conditionFields.map(field => `
              <option
                value="${e(field.id)}"
                ${field.id === edge.when.field ? 'selected' : ''}
              >
                ${e(field.label)}
              </option>
            `).join('')}
          </select>
        </label>


        <span class="finance-rule-is">
          is
        </span>


        <label>
          <span class="sr-only">
            Condition value
          </span>

          <select
            data-workflow-condition-value="${index}"
          >
            ${choices.map(choice => `
              <option
                value="${e(JSON.stringify(choice.value))}"
                ${
                  JSON.stringify(choice.value) ===
                  JSON.stringify(edge.when.equals)
                    ? 'selected'
                    : ''
                }
              >
                ${e(choice.label)}
              </option>
            `).join('')}
          </select>
        </label>

      </div>

    </div>
  `;
}


function workflowFriendlyEditor(layout) {
  const workflow = layout?.workflow;

  if (!workflow?.nodes?.length) {
    return `
      <div class="finance-step-welcome">
        <h2>Finance flow</h2>

        <p class="helper">
          There are no workflow steps yet.
        </p>
      </div>
    `;
  }


  if (!workflowNodeId) {
    return `
      <div class="finance-step-welcome">

        <p class="eyebrow">
          Finance flow
        </p>

        <h2>
          Choose a step
        </h2>

        <p>
          Select a step beside the Builder menu to see
          what it does and change its rules.
        </p>

        <div class="finance-flow-overview">
          ${workflowTree(layout)}
        </div>

      </div>
    `;
  }


  const node = workflow.nodes.find(
    item => item.id === workflowNodeId
  );


  if (!node) {
    workflowNodeId = '';
    return workflowFriendlyEditor(layout);
  }


  const incoming = (workflow.edges || []).filter(
    edge => edge.to === node.id
  );


  const outgoing = (workflow.edges || []).filter(
    edge => edge.from === node.id
  );


  return `
    <div class="finance-step-editor">

      <div class="finance-step-heading">

        <p class="eyebrow">
          ${e(workflowFriendlyType(node))}
        </p>

        <h2>
          ${e(workflowNodeLabel(layout, node))}
        </h2>

      </div>


      <details
        class="finance-step-section finance-step-disclosure"
        open
      >

        <summary>
          <span>Show when</span>

          <span
            class="finance-disclosure-chevron"
            aria-hidden="true"
          >
            ▾
          </span>
        </summary>


        <div class="finance-step-section-body">

          ${
            incoming.length
              ? incoming.map(edge =>
                  friendlyWorkflowConditionEditor(
                    layout,
                    edge,
                    workflow.edges.indexOf(edge)
                  )
                ).join('')
              : `
                  <p class="helper">
                    This is the first step, so it is
                    always shown first.
                  </p>
                `
          }

        </div>

      </details>


      <details
        class="finance-step-section finance-step-disclosure"
        open
      >

        <summary>
          <span>What happens next?</span>

          <span
            class="finance-disclosure-chevron"
            aria-hidden="true"
          >
            ▾
          </span>
        </summary>


        <div class="finance-step-section-body">

          ${
            outgoing.length
              ? outgoing.map(edge => {
                  const target = workflow.nodes.find(
                    item => item.id === edge.to
                  );

                  return `
                    <div class="finance-next-step">

                      ${
                        edge.when
                          ? `
                              <span>
                                When ${e(
                                  workflowCondition(
                                    edge,
                                    layout
                                  )
                                )}
                              </span>
                            `
                          : `
                              <span>
                                Next
                              </span>
                            `
                      }

                      <strong>
                        ${
                          target
                            ? e(
                                workflowNodeLabel(
                                  layout,
                                  target
                                )
                              )
                            : 'Finish'
                        }
                      </strong>

                    </div>
                  `;
                }).join('')
              : `
                  <p class="helper">
                    This is the end of the flow.
                  </p>
                `
          }

          <div class="builder-option-group" style="margin-top:14px">
            <label>Connect to
              <select id="workflow-connect-target">
                <option value="">Choose a step…</option>
                ${workflow.nodes.map(item => '<option value="' + e(item.id) + '">' + e(workflowNodeLabel(layout,item)) + '</option>').join('')}
              </select>
            </label>
            <label class="workflow-loop-option"><input type="checkbox" id="workflow-connect-loop"> Create as a repeat / loop connection</label><label>Maximum repeats <input id="workflow-connect-loop-limit" type="number" min="1" max="20" value="3"></label><button type="button" class="secondary-button" data-workflow-add-edge="${e(node.id)}">Add connection</button>
            <div class="workflow-edit-connections">
              ${(workflow.edges || []).map((edge,index) => '<div class="finance-next-step workflow-edge-editor"><div class="builder-two"><label>From<select data-workflow-edge-from="' + index + '">' + workflow.nodes.map(item => '<option value="' + e(item.id) + '"' + (item.id === edge.from ? ' selected' : '') + '>' + e(workflowNodeLabel(layout,item)) + '</option>').join('') + '</select></label><label>To<select data-workflow-edge-to="' + index + '">' + workflow.nodes.map(item => '<option value="' + e(item.id) + '"' + (item.id === edge.to ? ' selected' : '') + '>' + e(workflowNodeLabel(layout,item)) + '</option>').join('') + '</select></label></div>' + (edge.when ? '<small>Conditional · ' + e(workflowCondition(edge,layout)) + '</small>' : '<button type="button" class="secondary-button" data-workflow-make-conditional="' + index + '">Make conditional</button>') + '<label class="workflow-loop-option"><input type="checkbox" data-workflow-loop-toggle="' + index + '"' + (edge.action === "repeat" ? " checked" : "") + '> Repeat / loop</label><label>Maximum repeats <input type="number" min="1" max="20" value="' + e(String(edge.max_iterations || 3)) + '" data-workflow-loop-limit="' + index + '"' + (edge.action === "repeat" ? "" : " disabled") + '></label><div class="button-row"><button type="button" class="secondary-button" data-workflow-update-edge="' + index + '">Update connection</button><button type="button" class="secondary-button" data-workflow-remove-edge="' + index + '">Remove</button></div></div>').join('')}
            </div>
          </div>
        </div>

      </details>


      <details
        class="finance-step-advanced finance-step-disclosure"
      >

        <summary>
          <span>Advanced</span>

          <span
            class="finance-disclosure-chevron"
            aria-hidden="true"
          >
            ▾
          </span>
        </summary>


        <div class="finance-step-section-body">

          <dl class="workflow-node-details">

            <dt>Node ID</dt>

            <dd>
              <code>${e(node.id)}</code>
            </dd>


            <dt>Type</dt>

            <dd>
              ${e(node.type)}
            </dd>


            ${
              node.field_id
                ? `
                    <dt>Field ID</dt>

                    <dd>
                      <code>${e(node.field_id)}</code>
                    </dd>
                  `
                : ''
            }


            ${
              node.operation
                ? `
                    <dt>Operation</dt>

                    <dd>
                      <code>${e(node.operation)}</code>
                    </dd>
                  `
                : ''
            }

          </dl>

        </div>

      </details>

    </div>
  `;
}


function ensureFinanceBuilderStyles() {
  if (document.getElementById('align-finance-builder-v2')) {
    return;
  }

  const style = document.createElement('style');
  style.id = 'align-finance-builder-v2';

  style.textContent = `
    .builder-grid-no-preview {
      grid-template-columns: minmax(0, 1fr) !important;
    }

    .builder-grid-no-preview > .builder-panel {
      grid-column: 1 / -1;
      width: 100%;
      box-sizing: border-box;
    }

    .finance-flow-layout {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      gap: 22px;
      align-items: start;
      width: 100%;
      margin-top: 18px;
    }

    .finance-workflow-menu {
      position: sticky;
      top: 92px;
      min-width: 0;
      padding: 18px;
      border: 1px solid #e0e6f0;
      border-radius: 16px;
      background: #f7f9fc;
    }

    .finance-workflow-menu h3 {
      margin: 4px 0 4px;
      font-size: 18px;
    }

    .finance-workflow-menu .helper {
      margin-top: 5px;
    }

    .finance-workflow-step-list {
      display: grid;
      gap: 7px;
      margin-top: 16px;
    }

    .finance-workflow-step {
      display: grid;
      grid-template-columns: 34px minmax(0, 1fr) auto;
      align-items: center;
      gap: 10px;
      width: 100%;
      padding: 11px;
      border: 1px solid transparent;
      border-radius: 11px;
      background: transparent;
      color: #33435d;
      font: inherit;
      text-align: left;
      cursor: pointer;
    }

    .finance-workflow-step:hover {
      border-color: #d5def0;
      background: #fff;
    }

    .finance-workflow-step.is-selected {
      border-color: #7893eb;
      background: #eaf0ff;
      color: #294ec4;
      box-shadow: 0 1px 4px rgba(41,78,196,.08);
    }

    .finance-workflow-number {
      display: grid;
      place-items: center;
      width: 30px;
      height: 30px;
      border-radius: 9px;
      background: #fff;
      border: 1px solid #dce4ef;
      color: #6d7b90;
      font-size: 12px;
      font-weight: 750;
    }

    .finance-workflow-step.is-selected
    .finance-workflow-number {
      border-color: #89a0e8;
      color: #294ec4;
    }

    .finance-workflow-step-text {
      min-width: 0;
    }

    .finance-workflow-step-text strong,
    .finance-workflow-step-text small {
      display: block;
      overflow-wrap: anywhere;
    }

    .finance-workflow-step-text strong {
      font-size: 14px;
    }

    .finance-workflow-step-text small {
      margin-top: 3px;
      color: #7b879a;
      font-size: 11px;
    }

    .finance-workflow-arrow {
      color: #8591a5;
      font-size: 20px;
    }

    .finance-flow-editor {
      min-width: 0;
      min-height: 520px;
      padding: 4px 4px 30px;
    }

    .finance-step-welcome {
      max-width: 850px;
    }

    .finance-step-heading {
      margin-bottom: 24px;
    }

    .finance-step-heading h2 {
      margin: 4px 0 0;
      font-size: 27px;
    }

    .finance-step-section {
      margin-top: 18px;
      padding: 20px;
      border: 1px solid #e1e7ef;
      border-radius: 14px;
      background: #fff;
    }

    .finance-step-section h3 {
      margin: 0 0 14px;
      font-size: 16px;
    }

    .finance-rule {
      padding: 14px;
      border-radius: 12px;
      background: #f7f9fc;
    }

    .finance-rule-grid {
      display: grid;
      grid-template-columns: minmax(180px,1fr) auto minmax(180px,1fr);
      align-items: end;
      gap: 12px;
    }

    .finance-rule-grid label {
      display: grid;
      gap: 6px;
      color: #58677e;
      font-size: 12px;
      font-weight: 650;
    }

    .finance-rule-is {
      padding-bottom: 12px;
      color: #7d899b;
      font-size: 13px;
    }

    .finance-next-step {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      margin: 8px 0;
      padding: 13px 14px;
      border-radius: 11px;
      background: #f7f9fc;
    }

    .finance-next-step span {
      color: #68768c;
      font-size: 13px;
    }

    .finance-step-advanced {
      margin-top: 22px;
      padding: 14px 16px;
      border: 1px solid #e2e7ef;
      border-radius: 12px;
      background: #fbfcfe;
    }

    .finance-step-advanced summary {
      color: #596980;
      font-weight: 700;
      cursor: pointer;
    }

    .finance-flow-overview .workflow-tree {
      margin-top: 24px;
    }



    .finance-step-disclosure {
      overflow: hidden;
      padding: 0;
    }

    .finance-step-disclosure > summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      min-height: 56px;
      padding: 0 20px;
      border-radius: 14px;
      color: #31415a;
      font-size: 16px;
      font-weight: 700;
      cursor: pointer;
      list-style: none;
      user-select: none;
    }

    .finance-step-disclosure > summary::-webkit-details-marker {
      display: none;
    }

    .finance-step-disclosure > summary::marker {
      display: none;
      content: "";
    }

    .finance-step-disclosure > summary:hover {
      background: #f8faff;
    }

    .finance-step-section-body {
      padding: 0 20px 20px;
    }

    .finance-disclosure-chevron {
      display: inline-block;
      flex: 0 0 auto;
      color: #718099;
      font-size: 16px;
      transition: transform .16s ease;
    }

    .finance-step-disclosure[open]
    > summary
    .finance-disclosure-chevron {
      transform: rotate(180deg);
    }

    .finance-step-disclosure[open] > summary {
      margin-bottom: 6px;
    }

    .finance-step-advanced.finance-step-disclosure {
      margin-top: 18px;
      padding: 0;
    }

    .finance-step-advanced
    .workflow-node-details {
      margin-top: 4px;
    }

    @media (max-width: 1050px) {
      .finance-flow-layout {
        grid-template-columns: 240px minmax(0,1fr);
      }
    }

    @media (max-width: 780px) {
      .finance-flow-layout {
        grid-template-columns: 1fr;
      }

      .finance-workflow-menu {
        position: static;
      }

      .finance-rule-grid {
        grid-template-columns: 1fr;
      }

      .finance-rule-is {
        padding: 0;
      }
    }
  `;

  document.head.appendChild(style);
}


function financeEditor(layout) {
  ensureFinanceBuilderStyles();

  if (financeView === 'setup') {
    return `
      ${financeNav()}

      <h2>Finance</h2>

      <p class="helper">
        Change how Finance appears in Align.
      </p>

      <div data-layout-editor>

        ${input(
          'Name',
          'title',
          layout.title
        )}

        ${area(
          'Description',
          'description',
          layout.description
        )}

        <div class="field">
          <label>
            Record display

            <select data-prop="view">
              ${options(
                {
                  table: 'Table',
                  cards: 'Cards'
                },
                layout.view
              )}
            </select>
          </label>
        </div>

        <label>
          <input
            type="checkbox"
            data-prop="review_before_save"
            ${layout.review_before_save ? 'checked' : ''}
          >

          Show a review screen before saving
        </label>

      </div>
    `;
  }


  if (financeView === 'fields') {
    return `
      ${financeNav()}

      <h2>Finance questions</h2>

      <p class="helper">
        These are the questions people answer when
        adding a Finance item.
      </p>

      ${fieldList()}
    `;
  }


  if (financeView === 'flow') {
    if (
      workflowNodeId &&
      !layout.workflow?.nodes?.some(
        node => node.id === workflowNodeId
      )
    ) {
      workflowNodeId = '';
    }

    return `
      ${financeNav()}

      <div class="finance-flow-layout">

        ${workflowNodeMenu(layout)}

        <section
          class="finance-flow-editor"
          aria-label="Finance workflow editor"
        >
          ${workflowFriendlyEditor(layout)}
        </section>

      </div>
    `;
  }


  return `
    ${financeNav()}

    <h2>Finance preview</h2>

    <p class="helper">
      This is how the Finance form currently looks.
    </p>

    <div class="builder-preview">

      <h2>${e(layout.title)}</h2>

      <p>${e(layout.description)}</p>

      ${previewFields(layout.fields)}

    </div>

    <h3>Finance summary</h3>

    ${AlignFinance.summary(
      [{
        id: 'example',
        values: {
          category: 'Monthly payment / bill',
          name: 'Example bill',
          label: 'Home',
          next_payment: '2026-10-01',
          frequency: 'Monthly',
          payment_amount: 80,
          monthly_amount: 80
        }
      }],
      () => ''
    )}
  `;
}


function render(previewOnly=false) {
  if (!doc) return;
  const menuScrollTop = !previewOnly && tab === 'menus' && lastRenderedTab === 'menus'
    ? window.scrollY
    : null;

  document
    .querySelectorAll('[data-tab]')
    .forEach(button => {
      button.setAttribute(
        'aria-pressed',
        String(button.dataset.tab === tab)
      );
    });

  let editor = '';
  let preview = '';


  if (tab === 'overview') {
    editor = overview();
    preview = '';
  }


  else if (tab === 'review') {
    editor = review();

    preview = `
      <h2>Ready to publish?</h2>

      <p>
        Review your changes before publishing.
      </p>
    `;
  }


  else if (tab === 'startup') {
    editor = `
      <h2>Personal details first</h2>

      <p class="helper">
        Shown to new users after sign-in.
      </p>

      <div data-startup-editor>

        ${input(
          'Welcome title',
          'title',
          doc.startup.title
        )}

        ${area(
          'Welcome message',
          'description',
          doc.startup.description
        )}

        ${input(
          'Continue button',
          'button',
          doc.startup.button
        )}

      </div>

      ${fieldList()}
    `;

    preview = `
      <p class="builder-label">
        Startup preview
      </p>

      <div class="builder-preview">

        <h2>
          ${e(doc.startup.title)}
        </h2>

        <p>
          ${e(doc.startup.description)}
        </p>

        ${previewFields(doc.startup.fields)}

      </div>
    `;
  }


  else if (tab === 'menus') {
    editor = `
      <h2>Menu structure</h2>

      <p class="helper">
        Choose where things appear in Align.
      </p>

      ${
        menuTree() ||
        '<p class="builder-empty">No menus yet.</p>'
      }

      <button
        class="secondary-button"
        data-add-menu
      >
        Add menu item
      </button>

      ${menuEditor()}
    `;

    preview = `
      <p class="builder-label">
        Menu preview
      </p>

      <div class="builder-preview">
        ${
          menuPreview() ||
          '<p>No visible menu items.</p>'
        }
      </div>
    `;
  }


  else if (tab === 'base-structure') {
    editor = baseStructureEditor();

    preview = `
      <p class="builder-label">
        Base structure preview
      </p>
    `;
  }


  else if (tab === 'travel-results') {
    editor = travelResultsEditor();

    preview = `
      <p class="builder-label">
        Travel preview
      </p>

      <div class="builder-preview">
        <article class="card">
          <strong>
            Recommended journey
          </strong>

          <p>
            Leave 08:10 · Arrive 08:45
          </p>
        </article>
      </div>
    `;
  }


  else if (tab === 'home-nav') {
    editor = homeNavigationEditor();

    preview = `
      <p class="builder-label">
        Home preview
      </p>
    `;
  }


  else if (tab === 'layouts') {
    const layout = currentLayout();


    if (layout?.finance) {
      editor = financeEditor(layout);

      preview =
        financeView === 'flow' ||
        financeView === 'preview'
          ? ''
          : `
              <p class="builder-label">
                Preview
              </p>

              <div class="builder-preview">

                <h2>
                  ${e(layout.title)}
                </h2>

                <p>
                  ${e(layout.description)}
                </p>

                ${previewFields(layout.fields)}

              </div>
            `;
    }


    else {
      editor = `
        <h2>Sections</h2>

        <p class="helper">
          Create a section and its question matrix together. Each question becomes a column in the database and part of the guided entry form.
        </p>

        ${doc.layouts.map(item => `
          <div
            class="
              builder-row
              ${selected === item.id ? 'selected' : ''}
            "
          >

            <button
              class="builder-row-title"
              data-item="${e(item.id)}"
            >
              ${e(item.title)}

              <small>
                ${item.fields.length} fields
              </small>
            </button>

          </div>
        `).join('')}


        <button
          class="secondary-button"
          data-add-layout
        >
          Create section + input matrix
        </button>


        <button
          class="secondary-button"
          data-bills-template
        >
          Add Bills template
        </button>


        <button
          class="secondary-button"
          data-finance-template
        >
          Add Finance template
        </button>


        ${
          layout
            ? `
                <div
                  class="builder-editor"
                  data-layout-editor
                >

                  ${input(
                    'Layout name',
                    'title',
                    layout.title
                  )}

                  ${area(
                    'Description',
                    'description',
                    layout.description
                  )}

                  <p class="helper">Step 1 of 3 · Name this database. Next, add its questions and arrange the order people will answer them.</p>
                  ${layout.id==='work' ? `<section class="builder-editor"><h3>Link Work answers to Align</h3><p class="helper">Choose which questions mean Work Location, Shift Area, work date, and start/end times. These links let Align use your custom fields consistently.</p>${[['location','Work Location'],['area','Shift Area'],['date','Work date'],['start_time','Start time'],['end_time','End time']].map(([role,label])=>`<div class="field"><label>${label}<select data-work-association="${role}"><option value="">Not linked</option>${(layout.fields||[]).filter(field=>role==='date'?field.type==='date':['text','textarea','select'].includes(field.type)).map(field=>`<option value="${e(field.id)}" ${(layout.work_associations||{})[role]===field.id?'selected':''}>${e(field.label)}</option>`).join('')}</select></label></div>`).join('')}</section>` : ''}

                  <div class="field">
                    <label>
                      Record display

                      <select data-prop="view">
                        ${options(
                          {
                            table: 'Table',
                            cards: 'Cards'
                          },
                          layout.view
                        )}
                      </select>
                    </label>
                  </div>

                </div>

                <section class="section-matrix-setup">
                  <h3>Step 2 of 3 · Build the input matrix</h3>
                  <p class="helper">Add each piece of information people should enter. Choose a type, mark required answers, and move questions into the order that makes sense. Each question becomes a connected node in the form flow below.</p>
                  <div class="database-flow-workspace">
                    <div class="database-flow-editor-pane">
                      <div class="database-flow-pane-head"><p class="eyebrow">Edit the selected step</p><h3>Fields and questions</h3><p class="helper">Select a question here or click its node in the diagram to edit it.</p></div>
                      ${fieldList()}
                    </div>
                    <div class="database-flow-visual-pane">
                  <div class="database-flow-builder">
                    <div class="database-flow-head"><div><p class="eyebrow">Visual form flow</p><h3>${e(layout.title)} · input nodes</h3><p class="helper">Connect any node to any other node. Add multiple outgoing connections to create branches. The Form fields arrows still control the default question order.</p></div><button type="button" class="secondary-button" data-add-field>Add node</button></div>
                    <div class="database-flowchart database-flowchart-graph" aria-label="Database input flow nodes">
                      ${databaseFlowSvg(layout)}
                    </div>
                    <section class="database-flow-connections">
                      <h4>Connections</h4>
                      <p class="helper">Choose the source and destination independently. Connections are saved with this layout draft.</p>
                      <div class="database-flow-connect-controls">
                        <label>From<select id="database-flow-from">${databaseFlowOptions(layout, '__flow_start__')}</select></label>
                        <label>To<select id="database-flow-to">${databaseFlowOptions(layout, layout.fields?.[0]?.id || '__flow_finish__')}</select></label>
                        <button type="button" class="secondary-button" data-database-flow-add-edge>Add connection</button>
                      </div>
                      <div class="database-flow-edge-list">
                        ${databaseFlowEdges(layout).map((edge,index)=>`<div class="database-flow-edge"><strong>${e(databaseFlowLabel(layout,edge.from))} <span aria-hidden="true">→</span> ${e(databaseFlowLabel(layout,edge.to))}</strong><button type="button" class="secondary-button" data-database-flow-remove-edge="${index}">Remove</button></div>`).join('') || '<p class="helper">No connections yet. Add one above.</p>'}
                      </div>
                    </section>
                  </div>
                    </div>
                  </div>
                  ${layout.id==='work'?'<div class="builder-option-group"><h3>Work rota quick-input template</h3><p class="helper">Adds reusable location, area, day, and shift-time choices to Work without deleting existing questions or saved records.</p><button type="button" class="secondary-button" data-work-rota-template>Add rota quick-input fields</button></div>':''}
                </section>
                <section class="section-matrix-preview">
                  <h3>Step 3 of 3 · Review the entry form</h3>
                  <p class="helper">This preview follows the same question order and required settings used when someone creates a record.</p>
                  ${previewFields(layout.fields)}
                </section>
              `
            : ''
        }
      `;

      preview = layout
        ? `
            <p class="builder-label">
              Form preview
            </p>

            <div class="builder-preview">

              <h2>
                ${e(layout.title)}
              </h2>

              <p>
                ${e(layout.description)}
              </p>

              ${previewFields(layout.fields)}

            </div>
          `
        : `
            <p class="builder-empty">
              Choose a list.
            </p>
          `;
    }
  }


  if (
    previewOnly &&
    $('#builder-content aside')
  ) {
    $('#builder-content aside').innerHTML =
      preview;
  }

  else {
    const hidePreview =
      tab === 'overview' ||
      (tab === 'layouts' &&
      currentLayout()?.finance &&
      (
        financeView === 'flow' ||
        financeView === 'preview'
      ));

    $('#builder-content').innerHTML = `
      <div
        class="
          builder-grid
          ${hidePreview ? 'builder-grid-no-preview' : ''}
        "
      >

        <section class="builder-panel">
          ${editor}
        </section>

        ${
          hidePreview
            ? ''
            : `
                <aside
                  class="builder-panel"
                  aria-label="Preview"
                >
                  ${preview}
                </aside>
              `
        }

      </div>
    `;
  }


  const previewElement =
    $('#builder-content aside');

  if (previewElement) {
    AlignFormatting.apply(
      previewElement,
      doc.formatting
    );
  }


  if (
    !previewOnly &&
    $('[data-field-editor]')
  ) {
    const field =
      fields()?.find(
        item => item.id === fieldId
      );

    if (field) {
      const list = fields();

      const prior = list
        .slice(
          0,
          list.indexOf(field)
        )
        .filter(item =>
          ['select','checkbox']
            .includes(item.type)
        );

      $('[data-field-editor]')
        .insertAdjacentHTML(
          'beforeend',
          `
            ${
              field.type === 'select'
                ? `
                    <label>
                      <input
                        type="checkbox"
                        data-prop="allow_custom"
                        ${field.allow_custom ? 'checked' : ''}
                      >
                      Allow users to type a new choice
                    </label>
                  `
                : ''
            }

            <h4>
              Show this field when
            </h4>

            <p class="helper">
              Leave all choices unchecked
              to always show.
            </p>

            ${prior.map(previous => `
              <fieldset>

                <legend>
                  ${e(previous.label)}
                </legend>

                ${
                  (
                    previous.type === 'checkbox'
                      ? [false,true]
                      : previous.options
                  )
                  .map(value => `
                    <label
                      style="display:block"
                    >
                      <input
                        type="checkbox"
                        data-condition-field="${e(previous.id)}"
                        data-condition-value="${e(JSON.stringify(value))}"
                        ${
                          (
                            field.show_when?.[
                              previous.id
                            ] || []
                          ).includes(value)
                            ? 'checked'
                            : ''
                        }
                      >

                      ${
                        e(
                          typeof value === 'boolean'
                            ? (
                                value
                                  ? 'Checked'
                                  : 'Not checked'
                              )
                            : value
                        )
                      }

                    </label>
                  `).join('')
                }

              </fieldset>
            `).join('')}
          `
        );
    }
  }

  controls();
  lastRenderedTab = tab;
  if (menuScrollTop !== null) window.scrollTo(0, menuScrollTop);
}
  function move(list,item,direction) {const a=list.indexOf(item),b=a+direction;if(b>=0&&b<list.length)[list[a],list[b]]=[list[b],list[a]];}
  function newMenu(parent='') {changed();const m={id:id('menu'),parent_id:parent,title:'New menu item',description:'',icon:'○',colour:'#365CE6',destination:'note',layout_id:'',content:'',active:true};doc.menus.push(m);selected=m.id;fieldId='';render();}
  $('#builder-content').addEventListener('change', ev=>{
    const el=ev.target,key=el.dataset.prop||'';

    if(el.hasAttribute('data-workflow-condition-field')){
      const layout=currentLayout();
      const index=Number(el.dataset.workflowConditionField);
      const edge=layout?.workflow?.edges?.[index];

      if(!edge?.when) return;

      const nextField=layout.fields.find(
        field=>field.id===el.value
      );

      if(!nextField) return;

      changed();

      edge.when.field=nextField.id;
      edge.when.equals=
        nextField.type==='checkbox'
          ? false
          : (nextField.options?.[0] ?? '');

      status('Workflow condition changed. Save the draft when ready.');

      render();
      return;
    }

    if(el.hasAttribute('data-workflow-condition-value')){
      const layout=currentLayout();
      const index=Number(el.dataset.workflowConditionValue);
      const edge=layout?.workflow?.edges?.[index];

      if(!edge?.when) return;

      changed();

      edge.when.equals=JSON.parse(el.value);

      status('Workflow condition changed. Save the draft when ready.');

      render();
      return;
    }

    if(el.dataset.conditionField){changed();const field=fields().find(f=>f.id===fieldId);field.show_when={};el.closest('[data-field-editor]').querySelectorAll('[data-condition-field]:checked').forEach(x=>{(field.show_when[x.dataset.conditionField]||=[]).push(JSON.parse(x.dataset.conditionValue));});render();return;}
    if(el.dataset.workAssociation){changed();const layout=currentLayout();layout.work_associations=layout.work_associations||{};layout.work_associations[el.dataset.workAssociation]=el.value;status('Work association changed. Save the draft when ready.');return;}
    if(!key && !el.dataset.navProp && !el.dataset.sectionProp)return;
    if((tab==='home-nav'||tab==='base-structure') && key.startsWith('nav-title-')) { changed(); doc.navigation[Number(key.slice(10))].title=el.value; status('Unsaved changes. Save a draft or publish when ready.'); return; }
    if((tab==='home-nav'||tab==='base-structure') && key.startsWith('nav-icon-')) { changed(); doc.navigation[Number(key.slice(9))].icon=el.value; status('Unsaved changes. Save a draft or publish when ready.'); return; }
    if((tab==='home-nav'||tab==='base-structure') && key.startsWith('nav-destination-')) { const i=Number(key.slice(16)); changed(); doc.navigation[i].destination=el.value; if(el.value==='planner' && (!doc.navigation[i].title || doc.navigation[i].title==='New button')) { doc.navigation[i].title='Planner'; doc.navigation[i].icon='▦'; } status('Bottom button destination updated. Save a draft or publish when ready.'); render(); return; }
    if((tab==='home-nav'||tab==='base-structure') && key.startsWith('section-title-')) { const ordered=(doc.home_sections||[]).slice().sort((a,b)=>a.sort_order-b.sort_order); changed(); ordered[Number(key.slice(14))].title=el.value; status('Unsaved changes. Save a draft or publish when ready.'); return; }
    if(el.dataset.navProp) { changed(); doc.navigation[Number(el.dataset.navIndex)].active=el.checked; render(); return; }
    if(el.dataset.sectionProp) { changed(); doc.home_sections.slice().sort((a,b)=>a.sort_order-b.sort_order)[Number(el.dataset.sectionIndex)].visible=el.checked; render(); return; }
    if(el.dataset.baseWeather) { changed(); doc.base_structure=doc.base_structure||{}; doc.base_structure.weather=doc.base_structure.weather||{}; doc.base_structure.weather[el.dataset.baseWeather]=el.type==='checkbox'?el.checked:el.dataset.baseWeather==='refresh_minutes'?Number(el.value):el.value; render(); return; }
    if(el.dataset.travelProp) { changed(); doc.travel_results=doc.travel_results||{}; doc.travel_results[el.dataset.travelProp]=el.checked; render(); return; }
    if(el.dataset.travelVisibility) { changed(); doc.travel_results=doc.travel_results||{}; doc.travel_results.visibility=doc.travel_results.visibility||{}; doc.travel_results.visibility[el.dataset.travelVisibility]=el.checked; render(); return; }
    let target=el.closest('[data-field-editor]')?fields()?.find(x=>x.id===fieldId):el.closest('[data-startup-editor]')?doc.startup:el.closest('[data-menu-editor]')?doc.menus.find(x=>x.id===selected):currentLayout();if(!target)return;
    if(key==='destination'&&target.destination==='submenu'&&el.value!=='submenu'&&doc.menus.some(x=>x.parent_id===target.id)){status('Move the child items out of this folder before changing its destination.',true);render();return;}
    changed();target[key]=el.type==='checkbox'?el.checked:key==='options'?el.value.split('\n').map(x=>x.trim()).filter(Boolean):el.value;
    status('Unsaved changes. Save a draft or publish when ready.');render(!['type','destination','parent_id'].includes(key));
  });
document.addEventListener('keydown', ev => {
  if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.closest?.('[data-database-flow-node]')) {
    ev.preventDefault();
    ev.target.closest('[data-database-flow-node]').dispatchEvent(new MouseEvent('click', {bubbles:true}));
  }
});

document.addEventListener('click',ev=>{
  const flowNode = ev.target.closest('[data-database-flow-node]');
  if (flowNode && doc && !busy) {
    const nodeId = flowNode.dataset.databaseFlowNode;
    const kind = flowNode.dataset.databaseFlowKind;
    if (kind === 'field') {
      fieldId = nodeId;
      render();
      requestAnimationFrame(() => document.querySelector('[data-field-editor]')?.scrollIntoView({behavior:'smooth',block:'nearest'}));
    } else {
      const selector = kind === 'start' ? '#database-flow-from' : '#database-flow-to';
      const control = document.querySelector(selector);
      if (control) {
        control.value = nodeId;
        control.focus();
        control.scrollIntoView({behavior:'smooth',block:'nearest'});
      }
    }
    return;
  }

  const b=ev.target.closest('button');

  if(!doc)return;

  if(!b||busy)return;

if(b.dataset.workflowNode) {
     workflowNodeId = b.dataset.workflowNode;
     render();
     return;
   }

   if (b.hasAttribute('data-workflow-update-edge')) {
     const layout = currentLayout(); const workflow = layout?.workflow;
     const index = Number(b.dataset.workflowUpdateEdge); const edge = workflow?.edges?.[index];
     const source = document.querySelector('[data-workflow-edge-from="' + index + '"]')?.value;
     const target = document.querySelector('[data-workflow-edge-to="' + index + '"]')?.value;
     if (!edge || !source || !target || source === target) { status('Choose two different workflow steps.', true); return; }
     if ((workflow.edges || []).some((item,i) => i !== index && item.from === source && item.to === target)) { status('That connection already exists.', true); return; }
     const proposed = (workflow.edges || []).filter((item,i) => i !== index).concat([{from:source,to:target}]);
     const adjacency = new Map();
     proposed.forEach(item => { if (!adjacency.has(item.from)) adjacency.set(item.from, []); adjacency.get(item.from).push(item.to); });
     const reaches = (from,to) => { const seen = new Set(); const stack = [from]; while (stack.length) { const current = stack.pop(); if (current === to) return true; if (seen.has(current)) continue; seen.add(current); (adjacency.get(current) || []).forEach(next => stack.push(next)); } return false; };
     if (reaches(target,source) && edge.action !== 'repeat') { status('That connection would create a workflow loop. Mark an intentional repeat as a bounded loop instead.', true); return; }
     const reachable = new Set(); const stack = [workflow.start_node];
     while (stack.length) { const current = stack.pop(); if (reachable.has(current)) continue; reachable.add(current); (adjacency.get(current) || []).forEach(next => stack.push(next)); }
     if (workflow.nodes.some(item => !reachable.has(item.id))) { status('That change would leave a workflow step disconnected. Reconnect every step before updating.', true); return; }
     changed(); edge.from = source; edge.to = target; if (edge.action === 'repeat') edge.max_iterations = Math.max(1, Math.min(20, Number(document.querySelector('[data-workflow-loop-limit="' + index + '"]')?.value || edge.max_iterations || 3)));
     status('Connection updated in the draft. Save the draft to keep it.'); render(); return;
   }

   if (b.hasAttribute('data-workflow-remove-edge')) {
     const layout = currentLayout();
     const index = Number(b.dataset.workflowRemoveEdge);
     if (!layout?.workflow?.edges?.[index]) return;
     changed(); layout.workflow.edges.splice(index, 1);
     status('Connection removed from the draft. Reconnect required paths before publishing.'); render(); return;
   }

   if (b.hasAttribute('data-workflow-make-conditional')) {
     const layout = currentLayout(); const workflow = layout?.workflow;
     const edge = workflow?.edges?.[Number(b.dataset.workflowMakeConditional)];
     const field = layout ? workflowConditionFields(layout)[0] : null;
     if (!edge || !field) { status('Add a select or checkbox field before creating a condition.', true); return; }
     changed(); edge.when = {field:field.id,equals:field.type === 'checkbox' ? true : (field.options?.[0] ?? '')};
     status('Conditional branch added. Select its field and value in the destination step’s Show when settings.'); render(); return;
   }

   if (b.hasAttribute('data-workflow-loop-toggle')) {
     const layout = currentLayout(); const index = Number(b.dataset.workflowLoopToggle); const edge = layout?.workflow?.edges?.[index];
     if (!edge) return;
     const checked = b.checked; changed();
     if (checked) { edge.action = 'repeat'; edge.max_iterations = Math.max(1, Math.min(20, Number(document.querySelector('[data-workflow-loop-limit="' + index + '"]')?.value || 3))); }
     else { delete edge.action; delete edge.max_iterations; }
     status(checked ? 'Bounded repeat loop enabled. Set a maximum of 1–20 repeats.' : 'Repeat loop removed from this connection.');
     render(); return;
   }

   if (b.hasAttribute('data-workflow-add-edge')) {
     const layout = currentLayout(); const workflow = layout?.workflow;
     const source = b.dataset.workflowAddEdge;
     const target = document.querySelector('#workflow-connect-target')?.value;
     const isLoop = Boolean(document.querySelector('#workflow-connect-loop')?.checked);
     const maxIterations = Math.max(1, Math.min(20, Number(document.querySelector('#workflow-connect-loop-limit')?.value || 3)));
     if (!workflow || !target || (source === target && !isLoop)) { status('Choose a different step, or enable repeat / loop for a self-connection.', true); return; }
     if ((workflow.edges || []).some(edge => edge.from === source && edge.to === target && Boolean(edge.action === 'repeat') === isLoop)) { status('That connection already exists.', true); return; }
     const proposed = (workflow.edges || []).concat([{from:source,to:target,...(isLoop ? {action:'repeat',max_iterations:maxIterations} : {})}]);
     const adjacency = new Map(); proposed.filter(edge => edge.action !== 'repeat').forEach(edge => { if (!adjacency.has(edge.from)) adjacency.set(edge.from, []); adjacency.get(edge.from).push(edge.to); });
     const reaches = (from,to) => { const seen = new Set(); const stack = [from]; while (stack.length) { const current = stack.pop(); if (current === to) return true; if (seen.has(current)) continue; seen.add(current); (adjacency.get(current) || []).forEach(next => stack.push(next)); } return false; };
     if (!isLoop && reaches(target,source)) { status('That connection would create a cycle. Enable repeat / loop and set a repeat limit to allow it.', true); return; }
     changed(); workflow.edges = workflow.edges || []; workflow.edges.push({from:source,to:target,...(isLoop ? {action:'repeat',max_iterations:maxIterations} : {})});
     status(isLoop ? 'Bounded repeat loop added to the draft.' : 'Connection added to the draft. Use Show when to add a condition.'); render(); return;
   }

if(b.hasAttribute('data-preview-create-layout')) {
  tab = 'layouts'; selected = ''; fieldId = '';
  changed();
  const layout = {id:id('layout'),title:'New section',description:'',view:'table',review_before_save:true,fields:[{id:id('field'),label:'Name',type:'text',required:true,help:'What should this entry be called?',options:[]},{id:id('field'),label:'Date',type:'date',required:false,help:'',options:[]}]};
  doc.layouts.push(layout); selected=layout.id; render();
  return;
}

if(b.dataset.previewEditLayout) {
  tab = 'layouts'; selected = b.dataset.previewEditLayout; fieldId = '';
  render();
  return;
}

  if(b.dataset.financeView) {
    financeView = b.dataset.financeView;
    workflowNodeId = '';
    render();
    return;
  }

    if(b.dataset.jump){tab=b.dataset.jump;selected=b.dataset.select||'';fieldId=b.dataset.selectField||'';render();return;}
    if(b.dataset.tab){tab=b.dataset.tab;selected='';fieldId='';workflowNodeId='';render();return;}
    if(b.hasAttribute('data-reset-base')) { changed(); const current=doc.base_structure||{}; doc.base_structure={version:1,navigation:copy(doc.navigation),home_sections:copy(doc.home_sections),formatting:copy(doc.formatting),travel_results:copy(doc.travel_results),weather:{enabled:true,refresh_minutes:15,show_last_updated:true,show_errors:true,views:['today','hourly','daily']}}; tab='base-structure'; status('Base structure reset locally. Save a draft to keep it.'); render(); return; }
    if(b.hasAttribute('data-reset-travel')) { changed(); doc.travel_results={show_best_only:true,show_more:true,visibility:{leave_by:true,departure_arrival:true,duration:true,mode_provider:true,weather_adjustment:true,traffic_adjustment:true,actions:true}}; tab='travel-results'; status('Travel display defaults reset locally. Save a draft to keep it.'); render(); return; }
    if(b.dataset.navMove){changed();move(doc.navigation,doc.navigation[Number(b.dataset.navMove)],Number(b.dataset.dir));render();return;}
    if(b.dataset.sectionMove){const ordered=(doc.home_sections||[]).slice().sort((a,b)=>a.sort_order-b.sort_order),item=ordered[Number(b.dataset.sectionMove)],other=ordered[Number(b.dataset.sectionMove)+Number(b.dataset.dir)];if(other){changed();const t=item.sort_order;item.sort_order=other.sort_order;other.sort_order=t;render();}return;}
    if(b.hasAttribute('data-add-home-section')){const select=$('#add-home-section'),sectionId=select?.value;if(!sectionId)return;const available={today:{title:'Today at a glance',content:{show_weather:true,show_schedule:true,show_quick_add:true}},stats:{title:'Week summary',content:{}},menus:{title:'Your sections',content:{}},upcoming:{title:'Upcoming Events',content:{group_by_day:true}},calendar:{title:'Calendar',content:{show_upcoming:true}},annual_leave:{title:'Annual leave',content:{}}};if(!available[sectionId]||(doc.home_sections||[]).some(s=>s.id===sectionId))return;changed();doc.home_sections=doc.home_sections||[];doc.home_sections.push({id:sectionId,title:available[sectionId].title,visible:true,sort_order:Math.max(0,...doc.home_sections.map(s=>Number(s.sort_order)||0))+10,content:available[sectionId].content});status('Home section added. Save the draft, then publish when ready.');render();return;}
    if(b.dataset.removeHomeSection){if(!confirm('Remove this section from the home screen? Its underlying records and calendar events will be kept.'))return;changed();doc.home_sections=(doc.home_sections||[]).filter(s=>s.id!==b.dataset.removeHomeSection);status('Home section removed from the draft. Save the draft, then publish when ready.');render();return;}
    if(b.dataset.item){selected=b.dataset.item;fieldId='';workflowNodeId='';render();return;}
    if(b.dataset.field){fieldId=b.dataset.field;render();requestAnimationFrame(()=>document.querySelector('[data-field-editor]')?.scrollIntoView({behavior:'smooth',block:'nearest'}));return;}
    if(b.hasAttribute('data-add-menu'))newMenu();
    if(b.hasAttribute('data-add-child'))newMenu(selected);
    if (b.hasAttribute('data-database-flow-add-edge')) {
      const layout = currentLayout(); if (!layout) return;
      const from = document.querySelector('#database-flow-from')?.value;
      const to = document.querySelector('#database-flow-to')?.value;
      const nodes = databaseFlowNodes(layout);
      if (!nodes.some(node => node.id === from) || !nodes.some(node => node.id === to) || from === to) { status('Choose two different nodes for the connection.', true); return; }
      const edges = databaseFlowEdges(layout).map(edge => ({...edge}));
      if (edges.some(edge => edge.from === from && edge.to === to)) { status('Those nodes are already connected.', true); return; }
      const adjacency = new Map(); edges.forEach(edge => { if (!adjacency.has(edge.from)) adjacency.set(edge.from, []); adjacency.get(edge.from).push(edge.to); });
      const reaches = (start, target) => { const seen = new Set(); const stack = [start]; while (stack.length) { const current = stack.pop(); if (current === target) return true; if (seen.has(current)) continue; seen.add(current); (adjacency.get(current) || []).forEach(next => stack.push(next)); } return false; };
      if (reaches(to, from)) { status('That connection would create a loop. Choose another destination.', true); return; }
      changed(); layout.database_flow = layout.database_flow || {}; layout.database_flow.edges = edges.concat([{from, to}]);
      status('Connection added to the flowchart draft. Save the draft to keep it.'); render(); return;
    }
    if (b.hasAttribute('data-database-flow-remove-edge')) {
      const layout = currentLayout(); if (!layout) return;
      const index = Number(b.dataset.databaseFlowRemoveEdge); const edges = databaseFlowEdges(layout).map(edge => ({...edge}));
      if (!Number.isInteger(index) || !edges[index]) return;
      changed(); layout.database_flow = layout.database_flow || {}; layout.database_flow.edges = edges.filter((edge,i) => i !== index);
      status('Connection removed from the flowchart draft. Save the draft to keep it.'); render(); return;
    }
    if(b.hasAttribute('data-add-field')){changed();const f={id:id('field'),label:'New field',type:'text',required:false,help:'',options:[]};fields().push(f);fieldId=f.id;render();}
     if(b.hasAttribute('data-work-rota-template')){const layout=doc.layouts.find(item=>item.id==='work');if(!layout)return;const definitions=[
       {id:'rota_location',label:'Work location',type:'select',required:true,help:'Choose where this shift takes place.',options:['Arrowe Park','Clatterbridge','Community']},
       {id:'rota_area',label:'Work area',type:'select',required:true,help:'Choose the clinic, ward, or team.',options:['Wards','Clinic AM','Clinic PM','Hub AM','Community Clinic']},
       {id:'rota_day',label:'Day of week',type:'select',required:true,help:'Choose the day this shift repeats or takes place.',options:['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']},
       {id:'rota_start',label:'Shift start',type:'select',required:true,help:'Choose the start time.',options:['07:30','08:00','08:30','09:00','09:30','12:30','13:00','13:30']},
       {id:'rota_end',label:'Shift finish',type:'select',required:true,help:'Choose the finish time.',options:['11:30','12:00','12:30','13:00','13:30','16:30','17:00','17:30']}
     ];changed();layout.fields=layout.fields||[];const added=[];definitions.forEach(def=>{if(!layout.fields.some(field=>field.id===def.id)){layout.fields.push(def);added.push(def.id);}});layout.work_associations=layout.work_associations||{};Object.assign(layout.work_associations,{location:'rota_location',area:'rota_area',start_time:'rota_start',end_time:'rota_end'});selected='work';fieldId='';status(added.length?'Rota quick-input fields added. Existing fields and records were preserved. Save the draft, then publish when ready.':'Rota quick-input fields already exist.');render();return;}
    if(b.dataset.moveField){changed();move(fields(),fields().find(f=>f.id===b.dataset.moveField),Number(b.dataset.dir));render();}
    if(b.dataset.removeField&&confirm('Remove this field from the form? Previously saved values are retained.')){changed();const list=fields();list.splice(list.findIndex(f=>f.id===b.dataset.removeField),1);fieldId='';render();}
    if(b.dataset.move){changed();const m=doc.menus.find(x=>x.id===b.dataset.move),siblings=doc.menus.filter(x=>x.parent_id===m.parent_id),other=siblings[siblings.indexOf(m)+Number(b.dataset.dir)];if(other){const a=doc.menus.indexOf(m),c=doc.menus.indexOf(other);[doc.menus[a],doc.menus[c]]=[doc.menus[c],doc.menus[a]];}render();}
    if(b.hasAttribute('data-delete-menu')&&confirm('Delete this menu item? Its child items will move up one level. Records are retained.')){changed();const m=doc.menus.find(x=>x.id===selected);doc.menus.forEach(x=>{if(x.parent_id===selected)x.parent_id=m.parent_id;});doc.menus=doc.menus.filter(x=>x.id!==selected);selected='';render();}
    if(b.hasAttribute('data-bills-template')){changed();const l={id:id('layout'),title:'Bills',description:'Enter bill amounts and payments. Balance and totals calculate automatically.',view:'table',fields:[{id:'bill',label:'Bill',type:'text',required:true,help:'',options:[]},{id:'amount',label:'Amount',type:'number',required:true,help:'Amount due in pounds',options:[]},{id:'paid',label:'Paid',type:'number',required:true,help:'Enter 0 if unpaid',options:[]},{id:'balance',label:'Balance',type:'formula',formula:'[Amount] - [Paid]',required:false,help:'Calculated when saved',options:[]}]};doc.layouts.push(l);selected=l.id;fieldId='';doc.menus.push({id:id('menu'),parent_id:'',title:'Bills',description:'Bills and payments',icon:'£',colour:'#365CE6',destination:'layout',layout_id:l.id,content:'',active:true});render();}
    if(b.hasAttribute('data-add-layout')){changed();const l={id:id('layout'),title:'New section',description:'',view:'table',review_before_save:true,fields:[{id:id('field'),label:'Name',type:'text',required:true,help:'What should this entry be called?',options:[]},{id:id('field'),label:'Date',type:'date',required:false,help:'',options:[]}]};doc.layouts.push(l);selected=l.id;fieldId='';render();}
    if(b.hasAttribute('data-duplicate-layout')){changed();const l=copy(currentLayout());l.id=id('layout');l.title+=' copy';doc.layouts.push(l);selected=l.id;render();}
    if(b.hasAttribute('data-link-layout')){const l=currentLayout();newMenu();const m=doc.menus.find(x=>x.id===selected);m.title=l.title;m.description=l.description;m.destination='layout';m.layout_id=l.id;tab='menus';render();}
    if(b.hasAttribute('data-delete-layout')&&confirm('Delete this layout and its linked menu items? Existing user records are retained. Export the configuration first if you want to restore this layout later.')){changed();doc.layouts=doc.layouts.filter(x=>x.id!==selected);doc.menus=doc.menus.filter(x=>x.layout_id!==selected);selected='';fieldId='';render();}
  });
  async function save(publish) {
    if(publish&&!confirm('Publish these changes so everyone sees them? Saved records stay as they are.'))return;
    busy=true;controls();status(publish?'Publishing…':'Saving draft…');
    try{state=await api(publish?'/api/builder/publish':'/api/builder/config',{method:publish?'POST':'PUT',body:{revision:state.revision,document:doc}});doc=copy(state.draft);dirty=false;history=[];future=[];status(publish?`Published. People will see it when they refresh Align.`:`Draft saved. People will not see this until you publish.`);render();window.dispatchEvent(new CustomEvent('align-builder-config-updated',{detail:state}));}catch(err){status(err.message,true);}finally{busy=false;controls();}
  }
  $('#redo').onclick=()=>{if(inUnifiedDesign()||busy||!future.length)return;history.push(copy(doc));doc=future.pop();dirty=true;fieldId='';render();status('Change restored.');};
  $('#edit-search').oninput=()=>{tab='overview';render();};
  $('#preview-size').onchange=ev=>document.body.classList.toggle('phone-preview',ev.target.value==='phone');
  $('#save').onclick=()=>{if(!inUnifiedDesign())save(false);};$('#publish').onclick=()=>{if(!inUnifiedDesign())save(true);};
  $('#undo').onclick=()=>{if(!inUnifiedDesign()&&history.length){future.push(copy(doc));doc=history.pop();dirty=true;fieldId='';status('Last change undone.');render();}};
  $('#discard').onclick=()=>{if(!inUnifiedDesign()&&confirm('Replace your current draft with the published version?')){changed();doc=copy(state.published);selected='';fieldId='';render();status('Draft restored locally. Save draft to keep this change.');}};
  $('#export').onclick=()=>{if(inUnifiedDesign()||!doc)return;const url=URL.createObjectURL(new Blob([JSON.stringify(doc,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='align-layout-configuration.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  $('#import').onchange=async ev=>{if(inUnifiedDesign())return;try{const file=ev.target.files[0];if(!file)return;if(file.size>900000)throw Error('Configuration file is too large.');const imported=JSON.parse(await file.text());const result=await api('/api/builder/config',{method:'PUT',body:{revision:state.revision,document:imported}});state=result;doc=copy(result.draft);dirty=false;history=[];future=[];selected='';fieldId='';status('Configuration imported as a draft. Preview it before publishing.');render();window.dispatchEvent(new CustomEvent('align-builder-config-updated',{detail:state}));}catch(err){status(err.message,true);}finally{ev.target.value='';}};
  window.AlignBuilderStudio={hasUnsavedChanges:()=>dirty};
  window.addEventListener('align-studio-config-updated',event=>{
    const incoming=event.detail;
    if(!incoming?.draft||!incoming?.revision) return;
    if(dirty) {
      status('Save or discard Builder changes before applying the Studio update.',true);
      return;
    }
    state=incoming;doc=copy(incoming.draft);history=[];future=[];selected='';fieldId='';
    status('Studio draft updated.');render();
  });
  window.addEventListener('align-builder-tab',event=>{const next=event.detail?.tab;if(!['overview','startup','menus','home-nav','base-structure','layouts','travel-results','review'].includes(next))return;tab=next;selected='';fieldId='';workflowNodeId='';if(doc)render();});
  window.addEventListener('beforeunload',ev=>{if(dirty){ev.preventDefault();ev.returnValue='';}});
  api('/api/builder/config').then(data=>{state=data;doc=copy(data.draft);status('Ready. Choose a section on the left.');render();}).catch(err=>status(err.message+' Sign in as the owner, then open Studio again.',true));
document.addEventListener('keydown',ev=>{
  if(
    ev.key==='Escape' &&
    financeView==='flow' &&
    workflowNodeId
  ) {
    workflowNodeId='';
    render();
  }
});

})();

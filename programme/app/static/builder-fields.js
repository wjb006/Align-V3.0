/* Shared field rendering for the Owner preview and the live app. */
window.AlignFields = {
  escape(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); },
  render(fields, values = {}, prefix = 'entry') {
    const e = this.escape;
    return fields.map(f => {
      const id = `${prefix}-${f.id}`, value = values[f.id] ?? '', required = f.required ? 'required' : '';
      const visible = this.visible(f,values);
      const address = /\b(address|postcode|location|destination)\b/i.test(f.label || '') && ['text','textarea'].includes(f.type);
      const attrs = `id="${e(id)}" name="${e(f.id)}" ${required} ${visible?'':'disabled'}${address?` data-address-search="true" data-address-target="${e(id)}" autocomplete="street-address"`:''}`;
      let input;
      if (f.type === 'formula') input = `<input id="${e(id)}" name="${e(f.id)}" value="${e(value)}" readonly placeholder="Calculated on save"><small>${e(f.formula||'')}</small>`;
      else if (f.type === 'textarea') input = `<textarea ${attrs} maxlength="10000" rows="3">${e(value)}</textarea>`;
      else if (f.type === 'select' && f.allow_custom) input = `<input ${attrs} value="${e(value)}" list="${e(id)}-choices" maxlength="100"><datalist id="${e(id)}-choices">${f.options.map(o=>`<option value="${e(o)}"></option>`).join('')}</datalist>`;
      else if (f.type === 'select') input = `<select ${attrs}><option value="">Choose…</option>${f.options.map(o=>`<option value="${e(o)}" ${value===o?'selected':''}>${e(o)}</option>`).join('')}</select>`;
      else if (f.type === 'checkbox') input = `<input ${attrs} type="checkbox" ${value===true?'checked':''}>`;
      else input = `<input ${attrs} type="${e(f.type)}" value="${e(value)}" ${f.type==='number'?'step="any"':'maxlength="500"'} ${f.id==='user_name'?'autocomplete="name"':f.type==='tel'?'autocomplete="tel"':''}>`;
      return `<div class="field ${address?'address-search':''}" data-field-conditions="${e(JSON.stringify(f.show_when||{}))}" ${visible?'':'hidden'}><label for="${e(id)}">${e(f.label)}${f.required?' <span aria-label="required">*</span>':''}</label>${input}${address?`<div class="address-results" id="${e(id)}-results" data-address-results="${e(id)}" role="listbox" aria-label="Address suggestions"></div><small class="helper">Suggestions appear as you type. Your search text is sent to an address provider to find matches. You can also type it yourself.</small>`:''}${f.help?`<small class="helper">${e(f.help)}</small>`:''}</div>`;
    }).join('');
  },
  values(form, fields) {
    return Object.fromEntries(fields.filter(f=>f.type!=='formula').map(f => {const el=form.elements.namedItem(f.id);return [f.id,el.disabled?(f.type==='checkbox'?false:''):f.type==='checkbox'?el.checked:el.value];}));
  },
  visible(field,values) {return Object.entries(field.show_when||{}).every(([key,allowed])=>allowed.includes(values[key]??(allowed.includes(false)?false:'')));},
  display(value) { return typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value ?? ''); },
};

document.addEventListener('input',event=>{
  if(!event.target.closest('[data-field-conditions]'))return;
  const root=event.target.closest('form,.builder-preview');if(!root)return;
  const values={};
  root.querySelectorAll('[data-field-conditions]').forEach(row=>{
    const visible=AlignFields.visible({show_when:JSON.parse(row.dataset.fieldConditions)},values);
    row.hidden=!visible;
    row.querySelectorAll('input[name],select[name],textarea[name]').forEach(el=>{
      el.disabled=!visible;values[el.name]=visible?(el.type==='checkbox'?el.checked:el.value):(el.type==='checkbox'?false:'');
    });
  });
});

window.AlignFormatting = {
  defaults: {accent:'#365ce6',background:'#f5f7fb',surface:'#ffffff',text:'#1c2940',font:'system',size:'16',spacing:'comfortable',radius:'16',columns:'1',heading:'bold',align:'left'},
  apply(root, config) {
    if(!root)return;
    const f={...this.defaults,...config};
    root.classList.add('align-formatted');
    for(const key of ['accent','background','surface','text'])root.style.setProperty('--edit-'+key,/^#[0-9a-f]{6}$/i.test(f[key])?f[key]:this.defaults[key]);
    const values={font:{system:'system-ui, sans-serif',serif:'Georgia, serif',mono:'Consolas, monospace'},size:{14:'14px',16:'16px',18:'18px',20:'20px'},spacing:{compact:'10px',comfortable:'18px',roomy:'26px'},radius:{0:'0px',8:'8px',16:'16px',24:'24px'},columns:{1:'1',2:'2'},heading:{normal:'400',bold:'700'},align:{left:'left',center:'center'}};
    for(const [key,map] of Object.entries(values))root.style.setProperty('--edit-'+key,map[f[key]]||map[this.defaults[key]]);
  }
};

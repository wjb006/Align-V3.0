/* Shared field rendering for the Owner preview and the live app. */
window.AlignFields = {
  escape(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); },
  render(fields, values = {}, prefix = 'entry') {
    const e = this.escape;
    return fields.map(f => {
      const id = `${prefix}-${f.id}`;
      const rawValue = values[f.id] ?? '';
      const value = f.type === 'address' && rawValue && typeof rawValue === 'object' ? rawValue.label || '' : rawValue;
      const required = f.required ? 'required' : '';
      const visible = this.visible(f, values);
      const legacyAddressSearch = /\b(address|postcode|location|destination)\b/i.test(f.label || '') && ['text','textarea'].includes(f.type);
      const addressSearch = f.type === 'address' || legacyAddressSearch;
      const attrs = `id="${e(id)}" name="${e(f.id)}" ${required} ${visible?'':'disabled'}${addressSearch?` data-address-search="true" data-address-target="${e(id)}" autocomplete="street-address"`:''}${f.type === 'address'?' data-address-structured="true"':''}`;
      let input;
      if (f.type === 'formula') input = `<input id="${e(id)}" name="${e(f.id)}" value="${e(value)}" readonly placeholder="Calculated on save"><small>${e(f.formula||'')}</small>`;
      else if (f.type === 'textarea') input = `<textarea ${attrs} maxlength="10000" rows="3">${e(value)}</textarea>`;
      else if (f.type === 'select' && f.allow_custom) input = `<input ${attrs} value="${e(value)}" list="${e(id)}-choices" maxlength="100"><datalist id="${e(id)}-choices">${f.options.map(o=>`<option value="${e(o)}"></option>`).join('')}</datalist>`;
      else if (f.type === 'select') input = `<select ${attrs}><option value="">Choose…</option>${f.options.map(o=>`<option value="${e(o)}" ${value===o?'selected':''}>${e(o)}</option>`).join('')}</select>`;
      else if (f.type === 'checkbox') input = `<input ${attrs} type="checkbox" ${value===true?'checked':''}>`;
      else input = `<input ${attrs} type="${f.type === 'address' ? 'text' : e(f.type)}" value="${e(value)}" ${f.type==='number'?'step="any"':'maxlength="500"'} ${f.id==='user_name'?'autocomplete="name"':f.type==='tel'?'autocomplete="tel"':''}>`;
      return `<div class="field ${addressSearch?'address-search':''}" data-field-conditions="${e(JSON.stringify(f.show_when||{}))}" ${visible?'':'hidden'}><label for="${e(id)}">${e(f.label)}${f.required?' <span aria-label="required">*</span>':''}</label>${input}${addressSearch?`<div class="address-results" id="${e(id)}-results" data-address-results="${e(id)}" role="listbox" aria-label="Address suggestions" hidden></div><small class="helper">${f.type==='address'?'Start typing to find an address, or enter it manually.':'Suggestions may be available while you type.'} Search text is sent to the address provider.</small>`:''}${f.help?`<small class="helper">${e(f.help)}</small>`:''}</div>`;
    }).join('');
  },
  values(form, fields) {
    return Object.fromEntries(fields.filter(f=>f.type!=='formula').map(f => {
      const el=form.elements.namedItem(f.id);
      if (!el) return [f.id, f.type==='checkbox' ? false : ''];
      if (el.disabled) return [f.id, f.type==='checkbox' ? false : ''];
      if (f.type === 'checkbox') return [f.id, el.checked];
      if (f.type === 'address') {
        const label = String(el.value || '').trim();
        let selected = null;
        try { selected = el.dataset.addressValue ? JSON.parse(el.dataset.addressValue) : null; } catch (_) {}
        if (!label) return [f.id, ''];
        if (selected && selected.label === label) return [f.id, selected];
        return [f.id, {label, postcode:'', town:'', country:'', latitude:null, longitude:null, place_id:''}];
      }
      return [f.id, el.value];
    }));
  },
  visible(field,values) {return Object.entries(field.show_when||{}).every(([key,allowed])=>allowed.includes(values[key]??(allowed.includes(false)?false:'')));},
  display(value) {
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (value && typeof value === 'object') return String(value.label || '');
    return String(value ?? '');
  },
};

(() => {
  const timers = new WeakMap();
  const cache = new Map();
  let lastRequestAt = 0;
  let requestQueue = Promise.resolve();
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  async function lookup(query) {
    if (cache.has(query)) return cache.get(query);
    const run = requestQueue.then(async () => {
      const delay = Math.max(0, 1000 - (Date.now() - lastRequestAt));
      if (delay) await wait(delay);
      lastRequestAt = Date.now();
      const response = await fetch('/api/builder/address-search?q=' + encodeURIComponent(query), {headers:{'Accept':'application/json'},cache:'no-store'});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Address search is temporarily unavailable.');
      const items = Array.isArray(payload.results) ? payload.results : [];
      cache.set(query, items);
      if (cache.size > 40) cache.delete(cache.keys().next().value);
      return items;
    });
    requestQueue = run.catch(() => {});
    return run;
  }
  document.addEventListener('input', event => {
    const input = event.target.closest?.('[data-address-search]');
    if (!input) return;
    if (input.dataset.addressSelectionPending) {
      delete input.dataset.addressSelectionPending;
      return;
    }
    delete input.dataset.addressValue;
    const list = document.getElementById(input.id + '-results');
    if (!list) return;
    clearTimeout(timers.get(input));
    const query = input.value.trim();
    if (query.length < 3) {
      list.hidden = true;
      list.replaceChildren();
      return;
    }
    list.hidden = false;
    list.innerHTML = '<p class="address-results-status" role="status">Searching addresses…</p>';
    timers.set(input, setTimeout(async () => {
      try {
        const results = await lookup(query);
        if (input.value.trim() !== query) return;
        list.dataset.results = JSON.stringify(results);
        list.innerHTML = results.length ? results.map((item,index) =>
          `<button type="button" class="address-result" role="option" data-address-index="${index}"><strong>${String(item.label||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}</strong><small>${String([item.town,item.postcode].filter(Boolean).join(' · ')).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}</small></button>`
        ).join('') : '<p class="address-results-status">No matches found. You can still enter the address manually.</p>';
      } catch (error) {
        if (input.value.trim() !== query) return;
        list.innerHTML = '<p class="address-results-status" role="status">Address suggestions are unavailable. You can enter the address manually.</p>';
      }
    }, 700));
  });
  document.addEventListener('click', event => {
    const option = event.target.closest?.('[data-address-index]');
    if (option) {
      const list = option.closest('[data-address-results]');
      const input = list && document.getElementById(list.dataset.addressResults);
      if (!input || !list) return;
      let results = [];
      try { results = JSON.parse(list.dataset.results || '[]'); } catch (_) {}
      const item = results[Number(option.dataset.addressIndex)];
      if (!item) return;
      input.value = item.label || '';
      input.dataset.addressValue = JSON.stringify(item);
      input.dataset.addressSelectionPending = '1';
      list.hidden = true;
      input.dispatchEvent(new Event('input', {bubbles:true}));
      input.dispatchEvent(new Event('change', {bubbles:true}));
      input.focus();
      return;
    }
    if (!event.target.closest?.('.address-search')) {
      document.querySelectorAll('[data-address-results]').forEach(list => { list.hidden = true; });
    }
  });
  document.addEventListener('keydown', event => {
    const option = event.target.closest?.('[data-address-index]');
    if (option) {
      const list = option.closest('[data-address-results]');
      const options = list ? [...list.querySelectorAll('[data-address-index]')] : [];
      const index = options.indexOf(option);
      if (event.key === 'ArrowDown' && options.length) { event.preventDefault(); options[Math.min(index+1,options.length-1)].focus(); }
      else if (event.key === 'ArrowUp' && options.length) { event.preventDefault(); if(index<=0) document.getElementById(list.dataset.addressResults)?.focus(); else options[index-1].focus(); }
      else if (event.key === 'Escape') { event.preventDefault(); if(list) list.hidden=true; document.getElementById(list.dataset.addressResults)?.focus(); }
      return;
    }
    const input = event.target.closest?.('[data-address-search]');
    if (!input) return;
    const list = document.getElementById(input.id + '-results');
    if (!list || list.hidden) return;
    const options = [...list.querySelectorAll('[data-address-index]')];
    const active = options.indexOf(document.activeElement);
    if (event.key === 'ArrowDown' && options.length) { event.preventDefault(); options[Math.min(active+1,options.length-1)].focus(); }
    else if (event.key === 'ArrowUp' && options.length) { event.preventDefault(); if(active<=0) input.focus(); else options[active-1].focus(); }
    else if (event.key === 'Escape') { list.hidden = true; input.focus(); }
  });
})();

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

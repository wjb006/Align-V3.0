(() => {
  const $ = selector => document.querySelector(selector);
  const localStudio = ['127.0.0.1', 'localhost', '::1'].includes(location.hostname);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
  const copy = value => JSON.parse(JSON.stringify(value));
  const categories = {
    pages: {
      title: 'Pages & text',
      description: '',
      controls: []
    },
    colors: {
      title: 'Colours',
      description: 'Colours used across Align. Keep text easy to read.',
      controls: [['accent', 'Accent'], ['canvas', 'App background'], ['surface', 'Cards and surfaces'], ['text', 'Main text']]
    },
    banners: {
      title: 'Banners',
      description: 'Banner colours for the main planner sections.',
      controls: [['today', 'Today'], ['upcoming', 'Upcoming'], ['annual_leave', 'Annual leave'], ['section_detail', 'Personal sections']]
    },
    events: {
      title: 'Events',
      description: 'Event cards in the planner. The preview uses sample events.',
      controls: [['accent', 'Event marker']]
    },
    calendar: {
      title: 'Calendar',
      description: 'Month grid and list-day colours, plus week headings.',
      controls: [['month_cell', 'Month day cells'], ['month_weekend', 'Month weekend cells'], ['month_date_band', 'Month date band'], ['today_cell', 'Today highlight'], ['list_day', 'List day cards'], ['list_day_header', 'List day headers']]
    },
    type: {
      title: 'Text size',
      description: 'Text size, light or dark theme, and how round the corners are.',
      controls: []
    },
    history: {
      title: 'History',
      description: 'Earlier published designs. Bring one back into your draft, then publish if you want people to see it.',
      controls: []
    },
    users: {
      title: 'Personal choices',
      description: 'Choose what each person may change for themselves.',
      controls: []
    }
  };
  const permissionCopy = {
    colors: ['App colours', 'Let users change their own accent, background, card and text colours.'],
    banners: ['Section banners', 'Let users choose personal colours for Today, Upcoming, Annual leave and personal sections.'],
    events: ['Planner & events', 'Let users choose their event marker, card style and spacing.'],
    calendar: ['Calendar', 'Let users colour their own Month cells and List day cards.'],
    type: ['Text & shape', 'Let users adjust their own text size, font, headings and corner style.']
  };
  const presets = {
    classic: {label: 'Classic blue', colors: {accent:'#365ce6',canvas:'#f7f8fc',surface:'#ffffff',text:'#162147'}, banners: {today:'#172a62',upcoming:'#365ce6',annual_leave:'#0f9d8a',section_detail:'#365ce6'}, calendar: {month_cell:'#f1f5fd',month_weekend:'#e9eefb',month_date_band:'#dfe7fb',list_day:'#f1f5fd',list_day_header:'#edf2ff',today_cell:'#e4ecff'}},
    forest: {label: 'Forest', colors: {accent:'#2f7d5b',canvas:'#f4f8f5',surface:'#ffffff',text:'#14281f'}, banners: {today:'#1d4d38',upcoming:'#2f7d5b',annual_leave:'#b5651d',section_detail:'#2f7d5b'}, calendar: {month_cell:'#eef6f1',month_weekend:'#e3efe8',month_date_band:'#d3e6db',list_day:'#eef6f1',list_day_header:'#e0eee6',today_cell:'#d5ebdf'}},
    sunset: {label: 'Sunset', colors: {accent:'#c2410c',canvas:'#fbf7f4',surface:'#ffffff',text:'#2b1810'}, banners: {today:'#7c2d12',upcoming:'#c2410c',annual_leave:'#0f766e',section_detail:'#c2410c'}, calendar: {month_cell:'#fdf3ec',month_weekend:'#f9e8dc',month_date_band:'#f4dac8',list_day:'#fdf3ec',list_day_header:'#f9e8dc',today_cell:'#fbdcc6'}},
    slate: {label: 'Slate', colors: {accent:'#475569',canvas:'#f6f7f9',surface:'#ffffff',text:'#1e293b'}, banners: {today:'#1e293b',upcoming:'#475569',annual_leave:'#0e7490',section_detail:'#475569'}, calendar: {month_cell:'#f1f3f6',month_weekend:'#e8ebf0',month_date_band:'#dde2ea',list_day:'#f1f3f6',list_day_header:'#e8ebf0',today_cell:'#dbe3f0'}}
  };
  const lum = hex => {
    const v = (hex.slice(1).match(/.{2}/g) || ['33','33','33']).map(x => parseInt(x, 16) / 255)
      .map(x => x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4);
    return v[0] * 0.2126 + v[1] * 0.7152 + v[2] * 0.0722;
  };
  const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  function contrastNotes() {
    const a = documentDraft.appearance, notes = [];
    const check = (label, fg, bg) => { const r = contrast(fg, bg); if (r < 4.5) notes.push(`${label}: contrast ${r.toFixed(1)}:1 is below the recommended 4.5:1.`); };
    check('Main text on cards', a.colors.text, a.colors.surface);
    check('Main text on app background', a.colors.text, a.colors.canvas);
    check('Main text on Month cells', a.colors.text, a.calendar.month_cell);
    check('Main text on weekend cells', a.colors.text, a.calendar.month_weekend);
    check('Main text on List day cards', a.colors.text, a.calendar.list_day);
    for (const [k, c] of Object.entries(a.banners)) check(`Banner "${k.replaceAll('_', ' ')}" text`, lum(c) > 0.43 ? '#162147' : '#ffffff', c);
    return notes;
  }
  function applyPreset(key) {
    const p = presets[key];
    if (!p || !documentDraft) return;
    if (dirty && !window.confirm(`Apply the ${p.label} preset? It replaces your current colours (fonts and spacing are kept).`)) return;
    for (const cat of ['colors', 'banners', 'calendar']) Object.assign(documentDraft.appearance[cat], p[cat]);
    dirty = true; renderEditor(); renderPreview(); controls(); setStatus(`${p.label} preset applied — unsaved`, 'dirty');
  }
  let settings = null;
  function revertSection(cat) {
    const published = settings && settings.published && settings.published.appearance && settings.published.appearance[cat];
    if (!published || !documentDraft) return;
    documentDraft.appearance[cat] = JSON.parse(JSON.stringify(published));
    dirty = true; renderEditor(); renderPreview(); controls(); setStatus('Section reverted to the published design — unsaved', 'dirty');
  }
  let documentDraft = null;
  let activeTab = 'pages';
  let previewScreen = 'today';
  let dirty = false;
  let busy = false;
  let designActive = false;

  async function api(path, method = 'GET', body) {
    const token = sessionStorage.getItem('align-admin-token');
    const response = await fetch(path, {
      method,
      cache: 'no-store',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-Align-Admin': token } : {})
      },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    let result = {};
    try {
      result = await response.json();
    } catch (error) {
      if (response.ok) throw new Error('Align returned an unreadable response. Reload and try again.');
    }
    if (!response.ok) throw new Error(result.error || 'Unable to complete this action.');
    return result;
  }

  function studioNotice(message, state) {
    const toast = $('#studio-toast');
    if (!toast) return;
    if (state !== 'saved' && state !== 'error') {
      toast.hidden = true;
      return;
    }
    toast.dataset.state = state;
    toast.replaceChildren();
    const title = document.createElement('strong');
    title.textContent = state === 'error' ? 'Please check this' : (String(message).startsWith('Published') ? 'Published' : 'Saved');
    const detail = document.createElement('span');
    detail.textContent = message;
    toast.append(title, detail);
    toast.hidden = false;
    clearTimeout(studioNotice.timer);
    studioNotice.timer = setTimeout(() => { toast.hidden = true; }, 6500);
  }
  window.AlignStudioNotice = studioNotice;

  function setStatus(message, state = '') {
    const status = $('#management-status');
    status.textContent = message;
    status.dataset.state = state;
    if (state === 'saved' || state === 'error') studioNotice(message, state);
  }

  function labelActions() {
    $('#save').textContent = 'Save draft';
    $('#publish').textContent = 'Publish';
    const everyone = $('#publish-everyone');
    if (everyone) {
      everyone.hidden = !localStudio;
      everyone.textContent = 'Publish on the website';
    }
  }

  function controls() {
    labelActions();
    if (!designActive) return;
    $('#save').disabled = busy || !documentDraft || !dirty;
    const unpublishedDraft = settings && settings.revision !== settings.published_revision;
    $('#publish').disabled = busy || !documentDraft || (!dirty && !unpublishedDraft);
    const everyone = $('#publish-everyone');
    if (everyone) everyone.disabled = busy || !documentDraft || !localStudio;
    $('#discard').disabled = busy || !documentDraft || !dirty;
    $('#export').disabled = !documentDraft;
    $('#import').disabled = busy || !documentDraft;
    $('#undo').disabled = true;
    $('#redo').disabled = true;
  }

  function updateDocument(path, value) {
    const parts = path.split('.');
    let target = documentDraft;
    for (const part of parts.slice(0, -1)) target = target[part];
    target[parts.at(-1)] = value;
    dirty = true;
    controls();
    renderPreview();
    setStatus('Unsaved changes. Save a draft before you leave.', 'dirty');
  }

  function colorControls(category) {
    const values = documentDraft.appearance[category];
    return categories[category].controls.map(([key, label]) =>
      `<label class="management-control">${esc(label)}<input type="color" data-setting="appearance.${category}.${key}" value="${esc(values[key])}" aria-label="${esc(label)} colour"></label>`
    ).join('');
  }

  const areaContentControls = {
    today: [
      ['show_weather', 'Show weather'],
      ['show_schedule', 'Show today’s schedule'],
      ['show_quick_add', 'Show quick add'],
    ],
    upcoming: [
      ['group_by_day', 'Group events under day headings'],
    ],
  };
  const areaLabels = {
    today: 'Today',
    stats: 'Week summary',
    menus: 'Your sections',
    upcoming: 'Upcoming Events',
    annual_leave: 'Annual leave',
  };

  function pagesPanel() {
    if (!Array.isArray(documentDraft.home_sections)) documentDraft.home_sections = [];
    if (!Array.isArray(documentDraft.navigation)) documentDraft.navigation = [];
    const known = new Set(documentDraft.home_sections.map(section => section.id));
    for (const [id, title] of Object.entries(areaLabels)) {
      if (!known.has(id)) {
        documentDraft.home_sections.push({
          id, title, visible: id !== 'menus', sort_order: (documentDraft.home_sections.length + 1) * 10,
          content: Object.fromEntries((areaContentControls[id] || []).map(([key]) => [key, true])),
        });
      }
    }
    const sections = documentDraft.home_sections.slice().sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    const nav = documentDraft.navigation;
    const sectionRows = sections.map((section, index) => {
      const realIndex = documentDraft.home_sections.indexOf(section);
      if (!section.content || typeof section.content !== 'object') section.content = {};
      const kind = areaLabels[section.id] || section.id;
      const extras = (areaContentControls[section.id] || []).map(([key, label]) => {
        if (!(key in section.content)) section.content[key] = true;
        return `<label class="studio-line is-sub"><span>${esc(label)}</span><input class="management-toggle" type="checkbox" data-home-content="${realIndex}" data-content-key="${key}" ${section.content[key] ? 'checked' : ''}></label>`;
      }).join('');
      return `<div class="studio-line is-area">
          <span class="studio-line-kind">${esc(kind)}</span>
          <input maxlength="40" data-home-title="${realIndex}" value="${esc(section.title || '')}" aria-label="${esc(kind)} name">
          <label class="studio-line-check"><input class="management-toggle" type="checkbox" data-home-visible="${realIndex}" ${section.visible !== false ? 'checked' : ''}><span>Show</span></label>
          <span class="studio-line-move">
            <button type="button" data-home-move="${realIndex}" data-dir="-1" ${index === 0 ? 'disabled' : ''} aria-label="Move up">↑</button>
            <button type="button" data-home-move="${realIndex}" data-dir="1" ${index === sections.length - 1 ? 'disabled' : ''} aria-label="Move down">↓</button>
          </span>
        </div>${extras}`;
    }).join('');
    const navRows = nav.map((item, index) => `<div class="studio-line">
      <input class="studio-line-icon" maxlength="4" data-nav-icon="${index}" value="${esc(item.icon || '')}" aria-label="Icon">
      <input maxlength="40" data-nav-title="${index}" value="${esc(item.title || '')}" aria-label="Button name">
      <label class="studio-line-check"><input class="management-toggle" type="checkbox" data-nav-active="${index}" ${item.active !== false ? 'checked' : ''}> Show</label>
      <span class="studio-line-move">
        <button type="button" data-nav-move="${index}" data-dir="-1" ${index === 0 ? 'disabled' : ''} aria-label="Move up">↑</button>
        <button type="button" data-nav-move="${index}" data-dir="1" ${index === nav.length - 1 ? 'disabled' : ''} aria-label="Move down">↓</button>
      </span>
    </div>`).join('');
    return `<section class="management-control-section"><h3>Home areas</h3><div class="studio-lines">${sectionRows || '<div class="studio-empty"><strong>No home areas yet</strong><p>They appear here once the home screen has sections.</p></div>'}</div></section>
      <section class="management-control-section"><h3>Bottom buttons</h3><div class="studio-lines">${navRows || '<div class="studio-empty"><strong>No buttons yet</strong><p>Add them from Home layout if this list is empty.</p></div>'}</div></section>`;
  }

  function appearancePanel(tab) {
    const detail = categories[tab];
    let content = '';
    if (tab === 'pages') {
      content = pagesPanel();
    } else if (tab === 'calendar') {
      const cal = documentDraft.appearance.calendar;
      content = `<section class="management-control-section"><h3>Calendar colours</h3><div class="management-control-grid">${colorControls('calendar')}
        <label class="management-control">Week headings in List<select data-setting="appearance.calendar.week_headings">${[['show','Show'],['hide','Hide']].map(([value,label]) => `<option value="${value}" ${cal.week_headings === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
      </div></section>`;
    } else if (tab === 'colors' || tab === 'banners') {
      content = `<section class="management-control-section"><h3>${tab === 'colors' ? 'App colours' : 'Section colours'}</h3><div class="management-control-grid">${colorControls(tab)}</div></section>`;
      if (tab === 'colors') content += '<p class="management-accessibility-note">Use the phone to check that text is easy to read before you publish.</p>';
    } else if (tab === 'events') {
      const event = documentDraft.appearance.events;
      const choice = (key, fallback) => event[key] || fallback;
      content = `<section class="management-control-section"><h3>Event cards</h3><p>These choices apply to Today, Upcoming, and the Planner. Publish when you want Align to use them.</p><div class="management-control-grid">${colorControls('events')}
        <label class="management-control">Card style<select data-setting="appearance.events.style">${[['standard','Standard'],['compact','Compact'],['tinted','Tinted']].map(([value,label]) => `<option value="${value}" ${event.style === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        <label class="management-control">Card spacing<select data-setting="appearance.events.density">${[['comfortable','Comfortable'],['compact','Compact']].map(([value,label]) => `<option value="${value}" ${event.density === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        <label class="management-control">Same location<select data-setting="appearance.events.location_banner">${[['on','One banner when they follow each other'],['off','Separate cards']].map(([value,label]) => `<option value="${value}" ${choice('location_banner','on') === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        <label class="management-control">Time<select data-setting="appearance.events.time_place">${[['left','On the left'],['right','On the right']].map(([value,label]) => `<option value="${value}" ${choice('time_place','left') === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        <label class="management-control">Time size<select data-setting="appearance.events.time_size">${[['large','Larger'],['standard','Standard']].map(([value,label]) => `<option value="${value}" ${choice('time_size','large') === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        <label class="management-control">Title<select data-setting="appearance.events.title_format">${[['location_area','Location · Area'],['area','Area only']].map(([value,label]) => `<option value="${value}" ${choice('title_format','location_area') === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
      </div></section>`;
    } else if (tab === 'type') {
      const type = documentDraft.appearance.type;
      content = `<section class="management-control-section"><h3>Reading comfort</h3><div class="management-control-grid">
        <label class="management-control">Text size<select data-setting="appearance.type.scale">${[['default','Default'],['large','Larger']].map(([value,label]) => `<option value="${value}" ${type.scale === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        <label class="management-control">Colour theme<select data-setting="appearance.type.theme">${[['light','Light'],['dark','Dark'],['auto','Match the user’s phone']].map(([value,label]) => `<option value="${value}" ${type.theme === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        <label class="management-control">Font style<select data-setting="appearance.type.font">${[['system','Standard'],['serif','Serif'],['rounded','Rounded'],['mono','Monospace']].map(([value,label]) => `<option value="${value}" ${type.font === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        <label class="management-control">Heading weight<select data-setting="appearance.type.heading">${[['bold','Bold'],['normal','Regular']].map(([value,label]) => `<option value="${value}" ${type.heading === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        <label class="management-control">Component corners<select data-setting="appearance.type.corners">${[['soft','Soft'],['square','Square']].map(([value,label]) => `<option value="${value}" ${type.corners === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
      </div></section>`;
    } else if (tab === 'history') {
      content = '<section class="management-control-section"><h3>Past designs</h3><p>Each publish keeps a copy here. Use one to put it back into your draft, then publish if you want people to see it.</p><div id="management-history" role="status">Loading past designs…</div></section>';
    } else {
      const permissions = documentDraft.appearance_permissions;
      content = `<section class="management-control-section"><h3>What people can change</h3><p>Turn a choice on to let each person set it for themselves. Turn it off and everyone uses the design you publish.</p>${Object.entries(permissionCopy).map(([key, [label, help]]) => `<label class="management-user-option"><span><strong>${esc(label)}</strong><small>${esc(help)}</small></span><input class="management-toggle" type="checkbox" role="switch" data-setting="appearance_permissions.${key}" ${permissions[key] ? 'checked' : ''} aria-label="Allow users to personalise ${esc(label)}"></label>`).join('')}</section><p class="management-accessibility-note">People find the choices you turn on under Settings → Personalise your app. Those changes stay in their own account.</p>`;
    }
    const notes = (tab === 'colors' || tab === 'banners' || tab === 'calendar') ? contrastNotes() : [];
    const warn = notes.length ? `<div class="management-contrast" role="status"><strong>Readability check</strong><ul>${notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul></div>` : '';
    const presetBar = tab === 'colors' ? `<section class="management-control-section"><h3>Ready-made colour sets</h3><div class="management-preset-row">${Object.entries(presets).map(([key, p]) => `<button type="button" class="management-preset" data-preset="${key}"><span style="background:${p.colors.accent}"></span><span style="background:${p.banners.today}"></span><span style="background:${p.calendar.month_cell}"></span>${esc(p.label)}</button>`).join('')}</div><p class="management-accessibility-note">A set changes colours, banners, and the calendar together. Nothing changes for people until you publish.</p></section>` : '';
    const revertBar = ['colors', 'banners', 'events', 'type', 'calendar'].includes(tab) && settings && settings.published && settings.published.appearance ? `<section class="management-control-section"><button type="button" class="management-preset" data-revert-section="${tab}">Put this section back to the live design</button></section>` : '';
    return `<h2 class="management-page-title">${esc(detail.title)}</h2><p class="management-page-copy">${esc(detail.description)}</p>${presetBar}${content}${revertBar}${warn}`;
  }

  function renderEditor() {
    $('#management-editor').innerHTML = appearancePanel(activeTab);
    document.querySelectorAll('[data-setting]').forEach(control => {
      control.addEventListener('input', onSettingChange);
      control.addEventListener('change', onSettingChange);
    });
    document.querySelectorAll('[data-home-title]').forEach(control => {
      control.addEventListener('input', () => {
        documentDraft.home_sections[Number(control.dataset.homeTitle)].title = control.value;
        dirty = true; controls(); renderPreview(); setStatus('Unsaved changes. Save a draft before you leave.', 'dirty');
      });
    });
    document.querySelectorAll('[data-home-visible]').forEach(control => {
      control.addEventListener('change', () => {
        documentDraft.home_sections[Number(control.dataset.homeVisible)].visible = control.checked;
        dirty = true; controls(); renderPreview(); setStatus('Unsaved changes. Save a draft before you leave.', 'dirty');
      });
    });
    document.querySelectorAll('[data-home-content]').forEach(control => {
      control.addEventListener('change', () => {
        const section = documentDraft.home_sections[Number(control.dataset.homeContent)];
        if (!section.content || typeof section.content !== 'object') section.content = {};
        section.content[control.dataset.contentKey] = control.checked;
        dirty = true; controls(); renderPreview(); setStatus('Unsaved changes. Save a draft before you leave.', 'dirty');
      });
    });
    document.querySelectorAll('[data-nav-title]').forEach(control => {
      control.addEventListener('input', () => {
        documentDraft.navigation[Number(control.dataset.navTitle)].title = control.value;
        dirty = true; controls(); renderPreview(); setStatus('Unsaved changes. Save a draft before you leave.', 'dirty');
      });
    });
    document.querySelectorAll('[data-nav-icon]').forEach(control => {
      control.addEventListener('input', () => {
        documentDraft.navigation[Number(control.dataset.navIcon)].icon = control.value;
        dirty = true; controls(); renderPreview(); setStatus('Unsaved changes. Save a draft before you leave.', 'dirty');
      });
    });
    document.querySelectorAll('[data-nav-active]').forEach(control => {
      control.addEventListener('change', () => {
        documentDraft.navigation[Number(control.dataset.navActive)].active = control.checked;
        dirty = true; controls(); renderPreview(); setStatus('Unsaved changes. Save a draft before you leave.', 'dirty');
      });
    });
    document.querySelectorAll('[data-home-move]').forEach(button => button.addEventListener('click', () => {
      const ordered = documentDraft.home_sections.slice().sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
      const index = ordered.indexOf(documentDraft.home_sections[Number(button.dataset.homeMove)]);
      const other = ordered[index + Number(button.dataset.dir)];
      if (!other) return;
      const current = ordered[index];
      const temp = current.sort_order; current.sort_order = other.sort_order; other.sort_order = temp;
      dirty = true; renderEditor(); renderPreview(); controls(); setStatus('Unsaved changes. Save a draft before you leave.', 'dirty');
    }));
    document.querySelectorAll('[data-nav-move]').forEach(button => button.addEventListener('click', () => {
      const index = Number(button.dataset.navMove);
      const other = index + Number(button.dataset.dir);
      if (other < 0 || other >= documentDraft.navigation.length) return;
      const items = documentDraft.navigation;
      [items[index], items[other]] = [items[other], items[index]];
      dirty = true; renderEditor(); renderPreview(); controls(); setStatus('Unsaved changes. Save a draft before you leave.', 'dirty');
    }));
    if (activeTab === 'history') loadHistory();
    document.querySelectorAll('[data-revert-section]').forEach(button => button.addEventListener('click', () => revertSection(button.dataset.revertSection)));
    document.querySelectorAll('[data-preset]').forEach(button => button.addEventListener('click', () => applyPreset(button.dataset.preset)));
    syncStudioNav();
  }

  function syncStudioNav() {
    const pane = $('#design-pane');
    const designVisible = Boolean(designActive) && Boolean(pane) && !pane.hidden;
    document.querySelectorAll('.management-nav-item, [data-unified-tab], [data-management-tab]').forEach(button => {
      if (!designVisible && !button.classList.contains('management-nav-item')) return;
      const tab = button.dataset.unifiedTab || button.dataset.managementTab;
      const active = tab === activeTab;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  }

  async function loadHistory() {
    const box = $('#management-history');
    if (!box) return;
    try {
      const { history } = await api('/api/builder/history');
      if (activeTab !== 'history' || !$('#management-history')) return;
      box.innerHTML = history.length
        ? `<ul class="management-history-list">${history.map(item => `<li><span><strong>Published design</strong><small>Version ${esc(item.revision)} · ${esc(item.at ? formatDisplayDateTime(item.at) : 'time not recorded')}</small></span><button type="button" class="management-secondary" data-restore="${item.index}">Use this design</button></li>`).join('')}</ul>`
        : '<div class="studio-empty"><strong>No past designs yet</strong><p>When you publish, a copy is kept here so you can come back to it.</p></div>';
      box.querySelectorAll('[data-restore]').forEach(button => button.addEventListener('click', () => restoreDesign(Number(button.dataset.restore))));
    } catch (error) {
      box.innerHTML = `<div class="management-error"><strong>History could not be loaded.</strong><p>${esc(error.message)}</p></div>`;
    }
  }

  async function restoreDesign(index) {
    if (busy) return;
    if (dirty && !window.confirm('Replace your unsaved edits with this earlier design?')) return;
    setBusy(true);
    try {
      settings = await api('/api/builder/restore', 'POST', { index });
      documentDraft = copy(settings.draft);
      dirty = false;
      window.dispatchEvent(new CustomEvent('align-studio-config-updated', { detail: settings }));
      renderEditor();
      renderPreview();
      setStatus('That design is back in your draft. Publish when you want people to see it.', 'saved');
    } catch (error) {
      setStatus(error.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  function previewStyle() {
    const appearance = documentDraft.appearance;
    const colors = appearance.colors;
    const events = appearance.events;
    const type = appearance.type;
    const bannerKey = previewScreen === 'today' ? 'today' : 'upcoming';
    const cal = appearance.calendar;
    const bannerColor = appearance.banners[bannerKey];
    const channels = bannerColor.slice(1).match(/.{2}/g).map(value => parseInt(value, 16) / 255);
    const luminance = channels.map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2)
      .reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
    const bannerInk = luminance > 0.43 ? '#162147' : '#ffffff';
    const eventSurface = events.style === 'tinted' ? `${events.accent}22` : colors.surface;
    return [
      `--preview-accent:${colors.accent}`,
      `--preview-canvas:${colors.canvas}`,
      `--preview-surface:${colors.surface}`,
      `--preview-text:${colors.text}`,
      `--preview-banner:${bannerColor}`,
      `--preview-banner-ink:${bannerInk}`,
      `--preview-event-accent:${events.accent}`,
      `--preview-event-surface:${eventSurface}`,
      `--preview-font:${({serif:'Georgia,serif',rounded:'ui-rounded,"Nunito",system-ui,sans-serif',mono:'ui-monospace,Consolas,monospace'})[type.font] || 'inherit'}`,
      `--preview-cal-cell:${cal.month_cell}`,
      `--preview-cal-weekend:${cal.month_weekend}`,
      `--preview-cal-band:${cal.month_date_band}`,
      `--preview-cal-today:${cal.today_cell}`,
      `--preview-cal-day:${cal.list_day}`,
      `--preview-cal-head:${cal.list_day_header}`,
      `--preview-radius:${type.corners === 'square' ? '3px' : '11px'}`,
      `--preview-type-size:${type.scale === 'large' ? '15.5px' : '14px'}`,
      `--preview-event-padding:${events.density === 'compact' || events.style === 'compact' ? '8px' : '11px'}`
    ].join(';');
  }

  function previewContent() {
    const upcomingTitle = (documentDraft.home_sections || []).find(section => section.id === 'upcoming')?.title || 'Upcoming Events';
    const nav = (documentDraft.navigation || []).filter(item => item.active !== false).slice(0, 5);
    if (previewScreen === 'calendar') {
      const cells = Array.from({length: 14}, (_, i) => `<span class="mp-cell${i % 7 > 4 ? ' is-weekend' : ''}${i === 9 ? ' is-today' : ''}"><i>${i + 1}</i>${i % 3 === 0 ? '<b></b>' : ''}</span>`).join('');
      const heading = documentDraft.appearance.calendar.week_headings === 'show' ? '<p class="mp-week">WEEK COMMENCING 5 OCT</p>' : '';
      return `<p class="management-phone-banner">MONTH VIEW</p><div class="mp-grid">${cells}</div>
        <p class="management-phone-banner">LIST VIEW</p>${heading}
        <div class="mp-day"><h4>Monday 5 October</h4><div class="management-phone-event"><time>09:00</time><span><strong>Appointment</strong><small>Personal · sample</small></span></div></div>
        <div class="mp-day"><h4>Tuesday 6 October</h4><div class="management-phone-event"><time>14:00</time><span><strong>Project review</strong><small>Personal · sample</small></span></div></div>`;
    }
    if (previewScreen === 'planner') {
      return `<p class="management-phone-banner">PLANNER · TUESDAY</p>
        <div class="management-phone-event"><time>09:00</time><span><strong>Appointment</strong><small>Personal · sample</small></span></div>
        <div class="management-phone-event"><time>11:30</time><span><strong>Personal plan</strong><small>Personal · fictional sample</small></span></div>
        <div class="management-phone-event"><time>14:00</time><span><strong>Project review</strong><small>Personal · sample</small></span></div>
        <p class="management-phone-banner">${esc(upcomingTitle).toUpperCase()}</p>
        <div class="mp-day"><h4>Thursday 8 October</h4>
          <div class="management-phone-event"><time>09:00</time><span><strong>Planning session</strong><small>fictional sample event</small></span></div>
          <div class="management-phone-event"><time>15:30</time><span><strong>Visit</strong><small>fictional sample event</small></span></div>
        </div>`;
    }
    const blocks = [...(documentDraft.home_sections || [])].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    const blockMarkup = blocks.filter(section => section.visible !== false).map(section => {
      const title = esc(section.title || section.id);
      let contents = '';
      if (section.id === 'today') {
        if (section.content?.show_weather !== false) contents += '<div class="management-phone-weather"><strong>Today’s weather</strong><span>Clear skies · sample preview</span></div>';
        if (section.content?.show_schedule !== false) contents += '<div class="management-phone-event"><time>09:00</time><span><strong>Appointment</strong><small>Personal · sample</small></span></div><div class="management-phone-event"><time>11:30</time><span><strong>Personal plan</strong><small>Personal · sample</small></span></div>';
      } else if (section.id === 'upcoming') {
        contents = '<div class="mp-day"><h4>Thursday 8 October</h4><div class="management-phone-event"><time>09:00</time><span><strong>Planning session</strong><small>Sample event</small></span></div><div class="management-phone-event"><time>15:30</time><span><strong>Visit</strong><small>Sample event</small></span></div></div>';
      } else if (section.id === 'menus') {
        contents = (documentDraft.layouts || []).slice(0, 3).map(layout => `<button type="button" class="management-phone-event mp-section-entry" data-preview-edit-layout="${esc(layout.id)}" aria-label="Edit ${esc(layout.title)} section and input matrix"><span><strong>${esc(layout.title)}</strong><small>${(layout.fields || []).length} questions · tap to design</small></span></button>`).join('') || '<button type="button" class="mp-empty mp-add-section" data-preview-create-layout>Add a section and input matrix</button>';
      } else if (section.id === 'annual_leave') {
        contents = '<div class="management-phone-event"><time>FRI</time><span><strong>Annual leave</strong><small>Sample entry</small></span></div>';
      } else {
        contents = '<p class="mp-empty">Sample content</p>';
      }
      return `<section class="mp-editable-block" data-preview-home-section="${esc(section.id)}" draggable="true"><button class="mp-drag-handle" type="button" aria-label="Select or drag ${title}">⠿</button><p class="management-phone-banner">${title.toUpperCase()}</p>${contents}</section>`;
    }).join('');
    return `<div class="management-phone-greeting-block"><p class="management-phone-date">Wednesday 7 October 2026</p><h3 class="management-phone-greeting">Good morning</h3></div>${blockMarkup || '<p class="mp-empty">Add a home area in Studio to preview it here.</p>'}`;
  }

  function renderPreviewFallback() {
    const phone = $('#management-phone');
    if (!phone) return;
    phone.innerHTML = `<div class="management-phone" data-theme="light">
      <header class="management-phone-header"><span>Align<small>Your day, in view</small></span><span aria-hidden="true">☰</span></header>
      <section class="management-phone-section"><h3>Today</h3>
        <div class="management-phone-event"><time>09:00</time><span><strong>Appointment</strong><small>Work · preview</small></span></div>
        <div class="management-phone-event"><time>11:30</time><span><strong>Personal plan</strong><small>Personal · preview</small></span></div>
        <p class="management-phone-banner">UPCOMING</p>
        <div class="management-phone-event"><time>THU</time><span><strong>Planning session</strong><small>Preview event</small></span></div>
      </section>
      <nav class="management-phone-nav"><strong>Today</strong><span>Inbox</span><span>Planner</span><span>More</span></nav>
    </div>`;
  }

  function renderPreview() {
    const colors = documentDraft.appearance.colors;
    const nav = (documentDraft.navigation || []).filter(item => item.active !== false).slice(0, 5);
    const navMarkup = nav.length
      ? nav.map((item, index) => `<button type="button" class="${index === 0 ? 'is-current' : ''}" data-preview-nav-id="${esc(item.id)}" draggable="true" aria-label="Select or drag ${esc(item.title || 'navigation button')}">${esc(item.icon || '')} ${esc(item.title || '')}</button>`).join('')
      : '<strong>Today</strong><span>Inbox</span><span>Planner</span><span>More</span>';
    $('#management-phone').innerHTML = `<div class="management-phone" data-theme="${documentDraft.appearance.type.theme === 'dark' ? 'dark' : 'light'}" style="${previewStyle()}">
      <header class="management-phone-header"><span>Align<small>Your day, in view</small></span><span aria-hidden="true">☰</span></header>
      ${previewContent()}
      <nav class="management-phone-nav" aria-label="Sample app navigation">${navMarkup}</nav>
    </div>`;
    $('#management-phone').style.background = documentDraft.appearance.type.theme === 'dark' ? '#10142a' : colors.canvas;
  }

  function reorderFromPreview(kind, sourceId, targetId) {
    if (!sourceId || !targetId || sourceId === targetId) return;
    const list = kind === 'home'
      ? [...(documentDraft.home_sections || [])].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
      : (documentDraft.navigation || []);
    const source = list.findIndex(item => item.id === sourceId);
    const target = list.findIndex(item => item.id === targetId);
    if (source < 0 || target < 0) return;
    const [item] = list.splice(source, 1);
    list.splice(target, 0, item);
    if (kind === 'home') list.forEach((section, index) => { section.sort_order = (index + 1) * 10; });
    else documentDraft.navigation = list;
    dirty = true;
    renderEditor();
    renderPreview();
    controls();
    setStatus('Preview order changed. Save a draft or publish when ready.', 'dirty');
  }

  const phone = $('#management-phone');
  let draggedPreviewItem = null;
  phone.addEventListener('click', event => {
    const sectionEntry = event.target.closest('[data-preview-edit-layout]');
    const createSection = event.target.closest('[data-preview-create-layout]');
    if (sectionEntry || createSection) {
      const nextTab = 'layouts';
      if (window.AlignManagementStudioNav?.activate) window.AlignManagementStudioNav.activate(nextTab);
      else window.dispatchEvent(new CustomEvent('align-builder-tab', {detail: {tab: nextTab}}));
      if (sectionEntry) {
        document.querySelector(`[data-item="${CSS.escape(sectionEntry.dataset.previewEditLayout)}"]`)?.click();
      } else {
        document.querySelector('[data-add-layout]')?.click();
      }
      document.querySelector('#builder-content [data-layout-editor]')?.scrollIntoView({block: 'start'});
      return;
    }
    const editTarget = event.target.closest('.management-phone-banner, .management-phone-event, .management-phone-weather, .management-phone-greeting, .management-phone-header, .mp-grid, .mp-cell, .mp-day, .management-phone-date');
    if (editTarget) {
      let tab = 'pages';
      if (editTarget.matches('.management-phone-banner')) tab = 'banners';
      else if (editTarget.matches('.management-phone-event')) tab = 'events';
      else if (editTarget.matches('.management-phone-weather')) tab = 'colors';
      else if (editTarget.matches('.mp-grid, .mp-cell, .mp-day')) tab = 'calendar';
      else if (editTarget.matches('.management-phone-header, .management-phone-greeting, .management-phone-date')) tab = 'pages';
      if (window.AlignManagementStudioNav?.activate) window.AlignManagementStudioNav.activate(tab);
      else window.dispatchEvent(new CustomEvent('align-builder-tab', {detail: {tab}}));
      const editor = document.querySelector('#management-editor');
      editor?.scrollIntoView({block: 'start', behavior: 'smooth'});
      let exactControl = null;
      if (tab === 'banners') {
        const section = editTarget.closest('[data-preview-home-section]');
        const sectionId = section?.dataset.previewHomeSection;
        const bannerKey = sectionId === 'upcoming' ? 'upcoming' : sectionId === 'annual_leave' ? 'annual_leave' : sectionId === 'today' ? 'today' : 'section_detail';
        exactControl = editor?.querySelector(`[data-setting="appearance.banners.${bannerKey}"]`);
      } else if (tab === 'events') {
        exactControl = editor?.querySelector('[data-setting="appearance.events.accent"]');
      } else if (tab === 'calendar') {
        exactControl = editor?.querySelector('[data-setting="appearance.calendar.week_headings"]') ||
          editor?.querySelector('[data-setting^="appearance.calendar."]');
      } else if (tab === 'colors') {
        exactControl = editor?.querySelector('[data-setting="appearance.colors.accent"]');
      } else if (tab === 'pages') {
        const homeBlock = editTarget.closest('[data-preview-home-section]');
        if (homeBlock) {
          const index = [...document.querySelectorAll('[data-home-title]')].findIndex(control =>
            Number(control.dataset.homeTitle) === documentDraft.home_sections.findIndex(item => item.id === homeBlock.dataset.previewHomeSection));
          exactControl = index >= 0 ? document.querySelector(`[data-home-title="${documentDraft.home_sections.findIndex(item => item.id === homeBlock.dataset.previewHomeSection)}"]`) : null;
        }
        if (!exactControl && editTarget.matches('.management-phone-header, .management-phone-greeting')) {
          exactControl = editor.querySelector('[data-home-title]');
        }
      }
      const targetControl = exactControl || editor?.querySelector('input:not([type="hidden"]), select, textarea, button');
      targetControl?.focus({preventScroll:true});
      targetControl?.scrollIntoView({block: 'center', behavior: 'smooth'});
      setStatus(`Preview selected: ${({pages:'Pages & text',banners:'Banners',events:'Events',calendar:'Calendar',colors:'Colours'})[tab]}. The closest matching control is focused; the preview updates as you edit.`);
      return;
    }
    const block = event.target.closest('[data-preview-home-section]');
    if (block) {
      if (window.AlignManagementStudioNav?.activate) window.AlignManagementStudioNav.activate('pages');
      activeTab = 'pages';
      renderEditor();
      const index = documentDraft.home_sections.findIndex(item => item.id === block.dataset.previewHomeSection);
      const input = [...document.querySelectorAll('[data-home-title]')].find(control => Number(control.dataset.homeTitle) === index);
      input?.focus();
      input?.scrollIntoView({block: 'nearest'});
      requestAnimationFrame(() => {
        const current = [...document.querySelectorAll('[data-home-title]')].find(control => Number(control.dataset.homeTitle) === index);
        if (current && document.activeElement !== current) current.focus({preventScroll: true});
      });
      return;
    }
    const nav = event.target.closest('[data-preview-nav-id]');
    if (nav) {
      if (window.AlignManagementStudioNav?.activate) window.AlignManagementStudioNav.activate('home-nav');
      else window.dispatchEvent(new CustomEvent('align-builder-tab', {detail: {tab: 'home-nav'}}));
      const index = documentDraft.navigation.findIndex(item => item.id === nav.dataset.previewNavId);
      const input = document.querySelector(`[data-prop="nav-title-${index}"]`) ||
        [...document.querySelectorAll('[data-nav-title]')].find(control => Number(control.dataset.navTitle) === index);
      input?.focus();
      input?.scrollIntoView({block: 'nearest'});
    }
  });
  phone.addEventListener('dragstart', event => {
    const block = event.target.closest('[data-preview-home-section]');
    const nav = event.target.closest('[data-preview-nav-id]');
    if (!block && !nav) return;
    draggedPreviewItem = block
      ? {kind: 'home', id: block.dataset.previewHomeSection}
      : {kind: 'nav', id: nav.dataset.previewNavId};
    event.dataTransfer?.setData('text/plain', draggedPreviewItem.id);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
  });
  phone.addEventListener('dragover', event => {
    if (event.target.closest('[data-preview-home-section],[data-preview-nav-id]')) event.preventDefault();
  });
  phone.addEventListener('drop', event => {
    const block = event.target.closest('[data-preview-home-section]');
    const nav = event.target.closest('[data-preview-nav-id]');
    const targetKind = block ? 'home' : nav ? 'nav' : '';
    const targetId = block?.dataset.previewHomeSection || nav?.dataset.previewNavId;
    if (draggedPreviewItem && targetKind === draggedPreviewItem.kind && targetId) {
      event.preventDefault();
      reorderFromPreview(targetKind, draggedPreviewItem.id, targetId);
    }
    draggedPreviewItem = null;
  });

  function onSettingChange(event) {
    const control = event.currentTarget;
    const value = control.type === 'checkbox' ? control.checked
      : control.type === 'color' ? control.value.toLowerCase()
        : control.value;
    updateDocument(control.dataset.setting, value);
  }

  function setBusy(value) {
    busy = value;
    controls();
  }

  async function persist(publish) {
    if (!documentDraft || busy) return;
    if (publish) {
      const issues = contrastNotes();
      const warning = issues.length ? `\n\nReadability warning:\n- ${issues.join('\n- ')}\n\nPublish anyway?` : '';
      const question = localStudio
        ? 'Publish this design on this computer?'
        : 'Publish this design to everyone on the website?';
      if (!window.confirm(`${question}${warning}`)) return;
    }
    setBusy(true);
    setStatus(publish ? (localStudio ? 'Publishing on this computer…' : 'Publishing to everyone on the website…') : 'Saving draft…', 'busy');
    try {
      settings = await api(publish ? '/api/builder/publish' : '/api/builder/config', publish ? 'POST' : 'PUT', {
        revision: settings.revision,
        document: documentDraft
      });
      documentDraft = copy(settings.draft);
      dirty = false;
      window.dispatchEvent(new CustomEvent('align-studio-config-updated', { detail: settings }));
      renderEditor();
      renderPreview();
      setStatus(publish
        ? (localStudio ? 'Published on this computer. Refresh Align to see it.' : 'Published to everyone on the website. They will see it when they refresh Align.')
        : 'Draft saved. Publish when you want people to see it.', 'saved');
    } catch (error) {
      setStatus(error.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function publishEveryone() {
    if (!localStudio || !documentDraft || busy) return;
    if (!window.confirm('Publish this design to everyone on the website? This computer will match it.')) return;
    setBusy(true);
    setStatus('Publishing to everyone on the website…', 'busy');
    try {
      settings = await api('/api/builder/publish-everyone', 'POST', {
        revision: settings.revision,
        document: documentDraft
      });
      documentDraft = copy(settings.draft);
      dirty = false;
      window.dispatchEvent(new CustomEvent('align-studio-config-updated', { detail: settings }));
      renderEditor();
      renderPreview();
      setStatus('Published to everyone on the website. They will see it when they refresh Align.', 'saved');
    } catch (error) {
      setStatus(error.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  function discard() {
    if (!settings || !documentDraft) return;
    if (dirty && !window.confirm('Discard the unsaved edits and reload the saved draft?')) return;
    documentDraft = copy(settings.draft);
    dirty = false;
    renderEditor();
    renderPreview();
    setStatus('Saved draft restored');
    controls();
  }

  renderPreviewFallback();

  async function initialize() {
    try {
      settings = await api('/api/builder/config');
      documentDraft = copy(settings.draft);
      activeTab = categories[activeTab] ? activeTab : 'colors';
      renderEditor();
      renderPreview();
      setStatus(settings.revision !== settings.published_revision ? 'Saved, but not published yet.' : 'This is the live design.');
      controls();
    } catch (error) {
      $('#management-editor').innerHTML = `<div class="management-error"><strong>Could not load the shared design.</strong><p>${esc(error.message)}</p><button class="management-secondary" type="button" id="management-retry">Try again</button></div>`;
      $('#management-retry').addEventListener('click', initialize);
      setStatus('Unable to load design', 'error');
    }
  }

  document.querySelectorAll('[data-preview-screen]').forEach(button => {
    button.addEventListener('click', () => {
      previewScreen = button.dataset.previewScreen;
      document.querySelectorAll('[data-preview-screen]').forEach(item => {
        const active = item === button;
        item.classList.toggle('is-active', active);
        item.setAttribute('aria-pressed', String(active));
      });
      if (documentDraft) renderPreview();
    });
  });
  $('#export').addEventListener('click', () => {
    if (!designActive || !documentDraft) return;
    const { appearance, appearance_permissions } = documentDraft;
    const blob = new Blob([JSON.stringify({ align_design: 1, appearance, appearance_permissions }, null, 2)], { type: 'application/json' });
    const link = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'align-design.json' });
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  });
  $('#import').addEventListener('change', async event => {
    if (!designActive) return;
    const file = event.target.files[0];
    event.target.value = '';
    if (!file || !documentDraft) return;
    try {
      if (file.size > 200000) throw new Error('That file is too large to be an Align design.');
      const data = JSON.parse(await file.text());
      if (data.align_design !== 1 || typeof data.appearance !== 'object') throw new Error('This is not an Align design file.');
      for (const [cat, values] of Object.entries(data.appearance)) {
        if (!documentDraft.appearance[cat] || typeof values !== 'object') throw new Error('The design file has unsupported settings.');
        Object.assign(documentDraft.appearance[cat], values);
      }
      if (data.appearance_permissions && typeof data.appearance_permissions === 'object') Object.assign(documentDraft.appearance_permissions, data.appearance_permissions);
      dirty = true; renderEditor(); renderPreview(); controls();
      setStatus('Design imported. Save a draft to keep it.', 'dirty');
    } catch (error) {
      setStatus(error.message, 'error');
    }
  });
  $('#discard').addEventListener('click', () => { if (designActive) discard(); });
  $('#save').addEventListener('click', () => { if (designActive) persist(false); });
  $('#publish').addEventListener('click', () => { if (designActive) persist(true); });
  if ($('#publish-everyone')) $('#publish-everyone').addEventListener('click', () => { if (designActive) publishEveryone(); });
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderPreviewFallback, { once: true });
  } else {
    renderPreviewFallback();
  }
  window.dispatchEvent(new Event('align-management-ready'));
  labelActions();
  initialize();
  window.AlignManagementStudio={
    activateDesign:(tab)=>{
      $('#builder-pane').hidden=true;
      $('#design-pane').hidden=false;
      $('#special-pane').hidden=true;
      designActive=true;
      activeTab=categories[tab] ? tab : 'colors';
      if(documentDraft) renderEditor();
      else syncStudioNav();
      controls();
    },
    deactivateDesign:()=>{
      designActive=false;
      const everyone=$('#publish-everyone');
      if(everyone) everyone.disabled=true;
      const shared=$('#management-status');
      if(shared) {
        shared.textContent=$('#builder-status')?.textContent || 'Management Studio ready';
        shared.dataset.state='';
      }
    },
    hasUnsavedChanges:()=>designActive&&dirty
  };
  window.addEventListener('align-builder-config-updated',event=>{
    const incoming=event.detail;
    if(!incoming?.draft||!incoming?.revision) return;
    const appearance=documentDraft&&dirty?copy(documentDraft.appearance):null;
    const permissions=documentDraft&&dirty?copy(documentDraft.appearance_permissions):null;
    const homeSections=documentDraft&&dirty?copy(documentDraft.home_sections||[]):null;
    const navigation=documentDraft&&dirty?copy(documentDraft.navigation||[]):null;
    settings=incoming;
    documentDraft=copy(incoming.draft);
    if(appearance) documentDraft.appearance=appearance;
    if(permissions) documentDraft.appearance_permissions=permissions;
    if(homeSections) documentDraft.home_sections=homeSections;
    if(navigation) documentDraft.navigation=navigation;
    renderEditor();
    renderPreview();
    controls();
  });
  window.addEventListener('align-studio-config-updated',event=>{
    const incoming=event.detail;
    if(!incoming?.draft||!incoming?.revision) return;
    settings=incoming;
    documentDraft=copy(incoming.draft);
    if(!dirty) { renderEditor(); renderPreview(); controls(); }
  });
  document.querySelectorAll('[data-management-tab]').forEach(button => {
    button.addEventListener('click', () => window.AlignManagementStudio.activateDesign(button.dataset.managementTab));
  });
})();

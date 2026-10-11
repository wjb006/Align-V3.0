(() => {
  const titleMap = {
    dashboard: 'Home',
    startup: 'Welcome screen',
    menus: 'Menus',
    'home-nav': 'Home layout',
    'base-structure': 'Shared details',
    layouts: 'Sections',
    'travel-results': 'Travel',
    pages: 'Pages & text',
    colors: 'Colours',
    banners: 'Banners',
    events: 'Events',
    calendar: 'Calendar',
    type: 'Text size',
    review: 'Check changes',
    users: 'Personal choices',
    owner: 'Owner settings & integrations',
    history: 'History',
    preview: 'How the preview works',
    builds: 'Older versions',
    publish: 'Publish'
  };
  const subtitleMap = {
    dashboard: 'Choose a section, then publish when it looks right.',
    startup: 'The first screen people see, and the questions on it.',
    menus: 'The sections people open, and where each one goes.',
    'home-nav': 'What appears on the home screen and the bottom buttons.',
    'base-structure': 'Shared home, buttons, and weather. Saved records stay as they are.',
    layouts: 'Create the sections and fields people can use in Align.',
    'travel-results': 'What a journey card shows.',
    pages: 'The words on the home screen and the bottom buttons.',
    colors: 'The colours used across Align. Check the phone before you publish.',
    banners: 'The coloured bars on Today, Upcoming, and other sections.',
    events: 'How event cards look in the planner. The phone uses sample events.',
    calendar: 'Month and list colours, plus week headings.',
    type: 'Text size, theme, and how round the corners are.',
    review: 'See what will change, then publish when it looks right.',
    users: 'Choose what each person may change for themselves.',
    owner: 'Manage account access, Microsoft invitations, and owner integrations.',
    history: 'Earlier published designs. You can bring one back into your draft.',
    preview: 'The phone on the right is a sample. It updates as you edit.',
    builds: 'Older published copies and notes.',
    publish: 'Check the draft, then publish on this computer or on the website.'
  };
  const placeFor = {
    dashboard: 'Set up', startup: 'Set up', menus: 'Set up', 'home-nav': 'Set up', layouts: 'Set up',
    'travel-results': 'Set up', 'base-structure': 'Set up', review: 'Set up',
    pages: 'Look', colors: 'Look', banners: 'Look', events: 'Look', calendar: 'Look', type: 'Look',
    users: 'People', owner: 'People', history: 'People'
  };
  const builderTabs = new Set(['dashboard', 'startup', 'menus', 'home-nav', 'base-structure', 'layouts', 'travel-results', 'review']);
  const designTabs = new Set(['pages', 'colors', 'banners', 'events', 'calendar', 'type', 'users', 'history']);
  let active = 'dashboard';
  const $ = s => document.querySelector(s);

  function activate(tab) {
    if (builderTabs.has(active) && !builderTabs.has(tab) && window.AlignBuilderStudio?.hasUnsavedChanges()) {
      $('#management-status').textContent = 'Save or undo your changes before opening another section.';
      $('#management-status').dataset.state = 'error';
      window.AlignStudioNotice?.('Save or undo your changes before opening another section.', 'error');
      return;
    }
    if (designTabs.has(active) && !designTabs.has(tab) && window.AlignManagementStudio?.hasUnsavedChanges()) {
      $('#management-status').textContent = 'Save or undo your changes before opening another section.';
      $('#management-status').dataset.state = 'error';
      window.AlignStudioNotice?.('Save or undo your changes before opening another section.', 'error');
      return;
    }
    active = tab;
    document.querySelectorAll('[data-unified-tab]').forEach(b => {
      const on = b.dataset.unifiedTab === tab;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-pressed', String(on));
    });
    const place = $('#unified-place');
    if (place) place.textContent = placeFor[tab] || 'Studio';
    $('#unified-title').textContent = titleMap[tab] || 'Management Studio';
    const subtitle = $('#unified-subtitle');
    if (subtitle) subtitle.textContent = subtitleMap[tab] || 'Change Align here, then publish when you want people to see it.';
    const welcome = $('#studio-welcome');
    if (welcome) welcome.hidden = tab !== 'dashboard';
    $('#builder-page-title').textContent = titleMap[tab] || 'Edit';
    $('#builder-pane').hidden = !builderTabs.has(tab);
    $('#design-pane').hidden = !designTabs.has(tab);
    $('#special-pane').hidden = builderTabs.has(tab) || designTabs.has(tab);
    const more = document.querySelector('.studio-more');
    if (more) more.open = false;
    const phone = $('.unified-phone');
    if (phone) phone.hidden = false;
    if (builderTabs.has(tab)) {
      if (window.AlignManagementStudio) window.AlignManagementStudio.deactivateDesign();
      const real = tab === 'dashboard' ? 'overview' : tab;
      window.dispatchEvent(new CustomEvent('align-builder-tab', { detail: { tab: real } }));
    } else if (designTabs.has(tab)) {
      if (window.AlignManagementStudio) window.AlignManagementStudio.activateDesign(tab);
    } else {
      if (window.AlignManagementStudio) window.AlignManagementStudio.deactivateDesign();
      ['save', 'publish', 'publish-everyone', 'undo', 'redo', 'discard', 'export', 'import'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.disabled = true;
      });
      renderSpecial(tab);
    }
  }

  function renderSpecial(tab) {
    const box = $('#special-content');
    if (tab === 'owner') {
      box.innerHTML = '<div id="owner"><div class="builder-panel studio-special"><h2>Owner settings</h2><p>Loading owner integrations and account controls…</p></div></div>';
      if (window.AlignOwnerAdmin?.load) window.AlignOwnerAdmin.load();
      return;
    }
    const copy = {
      preview: ['How the preview works', 'The phone on the right is a sample of Align. It updates while you edit, and it does not change anyone’s real day.'],
      builds: ['Older versions', 'Published copies and notes live with the build archive. Your current draft is still the one you can publish.'],
      publish: ['Publish', 'Check the draft, then use Publish. On this computer it updates local Align. Publish on the website sends the same design to everyone.']
    };
    const x = copy[tab] || ['Home', 'Choose a section on the left to begin.'];
    box.innerHTML = `<div class="builder-panel studio-special"><h2>${x[0]}</h2><p>${x[1]}</p></div>`;
  }

  document.getElementById('studio-update')?.addEventListener('click', async () => {
    const button = document.getElementById('studio-update');
    const status = $('#management-status');
    button.disabled = true;
    status.dataset.state = 'busy';
    status.textContent = 'Checking for updates…';
    try {
      const response = await fetch('/api/studio/update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: '{}'
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || 'The update did not finish.');
      status.dataset.state = 'saved';
      status.textContent = payload.summary || 'Already up to date.';
      window.AlignStudioNotice?.(status.textContent, 'saved');
      if (payload.changed) setTimeout(() => location.reload(), 900);
    } catch (error) {
      status.dataset.state = 'error';
      status.textContent = error.message;
      window.AlignStudioNotice?.(error.message, 'error');
    } finally {
      button.disabled = false;
    }
  });
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-unified-tab]');
    if (b) activate(b.dataset.unifiedTab);
  });
  window.AlignManagementStudioNav = { activate };
  activate('dashboard');
})();

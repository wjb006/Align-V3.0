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
    calendar: 'Calendar appearance',
    'working-calendar': 'Working calendar',
    type: 'Text size',
    review: 'Check changes',
    users: 'Personal choices',
    owner: 'Owner settings & integrations',
    history: 'History',
    preview: 'How the preview works',
    builds: 'Older versions',
    publish: 'Publish',
    app: 'Align app',
    host: 'Host overview'
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
    'working-calendar': 'Browse real saved Align events by month, week, day, or hourly schedule. This view does not publish design changes.',
    type: 'Text size, theme, and how round the corners are.',
    review: 'See what will change, then publish when it looks right.',
    users: 'Choose what each person may change for themselves.',
    owner: 'Manage account access, Microsoft invitations, and owner integrations.',
    history: 'Earlier published designs. You can bring one back into your draft.',
    preview: 'The phone on the right is a sample. It updates as you edit.',
    builds: 'Older published copies and notes.',
    publish: 'Check the draft, then publish on this computer or on the website.',
    app: 'Open the real Align application from inside Management Studio.',
    host: 'A safe starting point for service and integration health. Live checks and host actions must be connected to authorized server endpoints before they can be reported as operational.'
  };
  const placeFor = {
    dashboard: 'Set up', startup: 'Set up', menus: 'Set up', 'home-nav': 'Set up', layouts: 'Set up',
    'travel-results': 'Set up', 'base-structure': 'Set up', review: 'Set up',
    pages: 'Look', colors: 'Look', banners: 'Look', events: 'Look', calendar: 'Look', type: 'Look',
    users: 'People', owner: 'People', history: 'People'
  };
  const builderTabs = new Set(['dashboard', 'startup', 'menus', 'home-nav', 'base-structure', 'layouts', 'travel-results', 'review']);
  const workingTabs = new Set(['working-calendar']);
  const designTabs = new Set(['pages', 'colors', 'banners', 'events', 'calendar', 'type', 'users', 'history']);
  const navGroups = [...document.querySelectorAll('.unified-nav-group')];
  const mobileNav = window.matchMedia('(max-width:700px)');
  let active = 'dashboard';
  const $ = s => document.querySelector(s);

  function syncNavGroups(tab = active) {
    if (!mobileNav.matches) return;
    const activeButton = [...document.querySelectorAll('.unified-nav [data-unified-tab]')]
      .find(button => button.dataset.unifiedTab === tab);
    const activeGroup = activeButton?.closest('.unified-nav-group');
    if (activeGroup) navGroups.forEach(group => { group.open = group === activeGroup; });
  }

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
      if (b.closest('.unified-nav')) {
        if (on) b.setAttribute('aria-current', 'page');
        else b.removeAttribute('aria-current');
      }
    });
    syncNavGroups(tab);
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
      if (workingTabs.has(tab)) window.AlignStudioCalendar?.mount($('#special-content'));
    }
  }

  function renderSpecial(tab) {
    const box = $('#special-content');
    if (tab === 'app') {
      box.innerHTML = '<div class="builder-panel studio-special"><h2>Align app</h2><p>The app opens here using this server, so it can use the existing application session and backend. If it does not appear, open it directly in a new tab.</p><div class="studio-platform-actions"><a class="management-primary" href="/" target="_blank" rel="noopener">Open Align in a new tab</a></div><iframe title="Align application" src="/" loading="lazy" style="width:100%;height:min(72vh,900px);border:1px solid var(--line,#ddd);border-radius:12px;background:white"></iframe></div>';
      return;
    }
    if (tab === 'host') {
      box.innerHTML = `<div class="builder-panel studio-special">
        <h2>Host overview</h2>
        <p>This panel is a starting point, not a live health report. No service is marked healthy until an authorized check confirms it.</p>
        <div class="studio-platform-grid">
          <section><h3>Application</h3><p>The production Align service connected to this Studio.</p><a href="https://getalign.co.uk" target="_blank" rel="noopener">Open production app</a></section>
          <section><h3>Database</h3><p>Production data remains in the configured hosted database. Connection strings and credentials are never shown here.</p><span>Live check not connected</span></section>
          <section><h3>Transport &amp; OTP</h3><p>Existing routing, timetable feeds and OTP configuration must be preserved.</p><span>Live check not connected</span></section>
        </div>
        <section class="studio-release-panel" aria-labelledby="studio-release-title">
          <h3 id="studio-release-title">Send a software release</h3>
          <p>Choose a GitHub branch or tag. GitHub runs the release checks first; Render updates only if they pass. The production environment can pause for an additional approval if configured.</p>
          <div class="studio-release-controls">
            <label>Source branch or tag<input id="studio-release-ref" type="text" maxlength="100" autocomplete="off" spellcheck="false"></label>
            <label>Destination<select id="studio-release-target"><option value="production">Production · getalign.co.uk</option></select></label>
            <button id="studio-release-submit" class="management-primary" type="button" disabled>Run release checks</button>
          </div>
          <p id="studio-release-status" role="status" aria-live="polite">Checking local release access…</p>
          <p class="studio-release-footnote">Staging is not configured yet. GitHub CLI sign-in and Render credentials stay on their authorized services; this Studio does not display secrets.</p>
          <a href="https://github.com/wjb006/Align-V3.0/actions/workflows/deploy-align-v3.yml" target="_blank" rel="noopener">View release workflow</a>
        </section>
      </div>`;
      setupReleasePanel();
      return;
    }
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

  async function setupReleasePanel() {
    const input = $('#studio-release-ref');
    const button = $('#studio-release-submit');
    const status = $('#studio-release-status');
    if (!input || !button || !status) return;
    if (!['127.0.0.1', 'localhost', '::1'].includes(location.hostname)) {
      status.textContent = 'Software releases are available from the local Management Studio on this PC.';
      button.disabled = true;
      return;
    }
    const adminToken = sessionStorage.getItem('align-admin-token');
    const headers = adminToken ? {'X-Align-Admin': adminToken} : {};
    try {
      const response = await fetch('/api/studio/deploy-info', {
        cache: 'no-store',
        credentials: 'same-origin',
        headers
      });
      const info = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(info.error || 'Local release access is unavailable.');
      input.value = info.default_ref || '';
      status.textContent = info.reason || 'Release access checked.';
      button.disabled = !info.available;
    } catch (error) {
      status.textContent = error.message;
      button.disabled = true;
    }
    button.addEventListener('click', async () => {
      const ref = input.value.trim();
      if (!ref) {
        status.textContent = 'Enter a GitHub branch or tag first.';
        input.focus();
        return;
      }
      if (!window.confirm(`Start release checks for "${ref}" and send it to the production Align app if they pass?`)) return;
      button.disabled = true;
      status.textContent = 'Sending the release request to GitHub…';
      try {
        const response = await fetch('/api/studio/deploy', {
          method: 'POST',
          cache: 'no-store',
          credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', ...headers},
          body: JSON.stringify({ref, target: 'production'})
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.error || 'GitHub could not start the release.');
        status.textContent = result.summary || 'Release checks queued.';
        const link = document.createElement('a');
        link.href = result.workflow_url;
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = 'Open release workflow';
        status.append(' ', link);
      } catch (error) {
        status.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });
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
  mobileNav.addEventListener('change', () => {
    if (!mobileNav.matches) navGroups.forEach(group => { group.open = true; });
    else syncNavGroups();
  });
  window.AlignManagementStudioNav = { activate };
  activate('dashboard');
})();

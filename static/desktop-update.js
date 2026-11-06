(() => {
  function node(name, root) {
    return (root || document).querySelector(`[data-update="${name}"]`);
  }

  async function send(url, payload) {
    const response = await fetch(url, {
      method: payload ? 'POST' : 'GET',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: payload ? { 'Content-Type': 'application/json' } : undefined,
      body: payload ? JSON.stringify(payload) : undefined,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || 'Align could not check for updates.');
    return body;
  }

  function paint(status, root) {
    const copy = node('status', root) || document.getElementById('desktop-update-copy');
    const apply = node('apply', root);
    const launch = node('launch', root);
    const token = node('token', root);
    if (copy) {
      const build = status.build ? `Build ${status.build}. ` : '';
      const installed = status.installed_commit ? `Installed commit ${status.installed_commit.slice(0, 7)}. ` : 'No installed commit is recorded. ';
      const remote = status.remote_commit ? `Latest commit ${status.remote_commit.slice(0, 7)}. ` : '';
      copy.textContent = `${build}${installed}${remote}${status.summary || status.error || ''}`.trim();
    }
    if (apply) apply.hidden = !(status.install_offered || status.restart_required);
    if (launch) launch.checked = status.check_on_launch === true;
    if (token) {
      token.value = '';
      token.placeholder = status.token_saved ? 'A token is saved on this computer' : 'No token saved';
    }
    const section = document.getElementById('programme-update');
    if (section) section.hidden = false;
  }

  async function refresh() {
    const section = document.getElementById('programme-update');
    if (!section && !document.querySelector('[data-update="check"]')) return;
    try {
      paint(await send('/api/desktop/update'));
    } catch (error) {
      if (section) section.hidden = true;
      const copy = document.getElementById('desktop-update-copy');
      if (copy) copy.textContent = error.message;
    }
  }

  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-update]');
    if (!button || button.disabled) return;
    const action = button.dataset.update;
    if (action !== 'check' && action !== 'apply' && action !== 'save') return;
    button.disabled = true;
    try {
      if (action === 'check') {
        paint(await send('/api/desktop/update/check', {}));
        return;
      }
      if (action === 'save') {
        const token = node('token');
        const payload = { check_on_launch: Boolean(node('launch')?.checked) };
        if (token && token.value) payload.token = token.value;
        paint(await send('/api/desktop/update/settings', payload));
        return;
      }
      const staged = await send('/api/desktop/update/apply', {});
      paint(staged);
      if (!staged.restart_required) return;
      await send('/api/desktop/update/restart', {});
      const copy = node('status') || document.getElementById('desktop-update-copy');
      if (copy) copy.textContent = 'Restarting Align to load the update. Planner data on this computer is kept.';
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        try {
          const health = await fetch('/api/health', { cache: 'no-store' });
          if (health.ok) {
            location.reload();
            return;
          }
        } catch (error) {
          /* The server is restarting. */
        }
      }
    } catch (error) {
      const copy = node('status') || document.getElementById('desktop-update-copy');
      if (copy) copy.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });

  document.addEventListener('change', async event => {
    const box = event.target.closest('[data-update="launch"]');
    if (!box) return;
    try {
      paint(await send('/api/desktop/update/settings', { check_on_launch: box.checked }));
    } catch (error) {
      const copy = node('status') || document.getElementById('desktop-update-copy');
      if (copy) copy.textContent = error.message;
    }
  });

  window.AlignProgrammeUpdate = { refresh };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { void refresh(); });
  } else {
    void refresh();
  }
})();

(() => {
  const title = document.getElementById('desktop-status-title');
  const copy = document.getElementById('desktop-status-copy');
  const retry = document.getElementById('desktop-retry');

  async function readJson(url) {
    const response = await fetch(url, { cache: 'no-store', credentials: 'same-origin' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || 'Align could not be checked on this computer.');
    return body;
  }

  async function refresh() {
    title.textContent = 'Checking Align…';
    copy.textContent = 'Looking at the local server. The public website is not checked from here.';
    retry.disabled = true;
    try {
      const health = await readJson('/api/health');
      const status = await readJson('/api/desktop/status');
      const database = health.database || {};
      const ready = database.available === true && database.integrity === 'ok';
      const version = health.version || {};
      title.textContent = ready ? 'Ready on this computer' : 'Opened, with a database warning';
      const dataLine = status.database_present
        ? 'Planner data is saved on this computer.'
        : 'A new local database will be created on this computer as you use the planner.';
      copy.textContent = `Align ${version.app || ''} build ${version.build || ''} answered. ${dataLine} The public website was not checked.`;
    } catch (error) {
      title.textContent = 'Not ready';
      copy.textContent = error.message;
    } finally {
      retry.disabled = false;
    }
  }

  retry.addEventListener('click', () => { void refresh(); });
  void refresh();
})();

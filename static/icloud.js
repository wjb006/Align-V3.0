let cloudState = null;
let cloudBusy = false;
let cloudMessage = '';
let accountCredentialKey = null;
let cloudStatusPollTimer = 0;
function pollCloudSyncStatus(previousAttempt, polls = 0) {
  clearTimeout(cloudStatusPollTimer);
  if (polls >= 60) return;
  cloudStatusPollTimer = setTimeout(async () => {
    try {
      const updated = await api('/api/icloud/manage');
      const changed = JSON.stringify(updated) !== JSON.stringify(cloudState);
      cloudState = updated;
      if (changed) render();
      if (cloudState.busy || cloudState.last_attempt === previousAttempt) {
        pollCloudSyncStatus(previousAttempt, polls + 1);
      }
    } catch (error) {
      cloudMessage = error.message;
      render();
    }
  }, 1000);
}
function cloudSyncStatusMarkup(status) {
  if (!status) return '<p>Click Check connection to view its current state.</p>';
  const attempt = status.last_attempt ? `Last attempt: ${escapeHtml(formatDisplayDateTime(status.last_attempt))}` : '';
  const success = status.last_sync ? `Last successful sync: ${escapeHtml(formatDisplayDateTime(status.last_sync))}` : 'No successful sync yet.';
  const error = status.last_error
    ? `<p role="alert" class="planner-error">Last sync failed: ${escapeHtml(status.last_error)} Automatic retry in about ${Math.ceil((status.retry_in_seconds || 60) / 60)} minute${(status.retry_in_seconds || 60) >= 120 ? 's' : ''}; use Sync now to retry immediately.</p>`
    : '';
  const conflicts = (status.conflicts || []).length
    ? `<section class="planner-warning" role="status"><strong>iCloud conflicts — review needed</strong><ul>${(status.conflicts || []).map(item => `<li>${escapeHtml(item.message)}</li>`).join('')}</ul><p>Two-way sync continued for other events. Keep one version of each conflicted item, then use Sync now.</p></section>`
    : '';
  const calendars = (status.calendars || []).map(calendar => {
    const target = calendar.id === status.target;
    const label = target ? 'Align shift destination' : 'Read for clash checking';
    const detail = calendar.status === 'error'
      ? `Last attempt failed: ${escapeHtml(calendar.error || 'Calendar unavailable.')}`
      : calendar.status === 'syncing'
        ? 'Checking this calendar…'
        : calendar.status === 'ok'
          ? `Read ${calendar.event_count} events · last successful check ${escapeHtml(formatDisplayDateTime(calendar.last_success || ''))}`
          : 'Waiting for the first sync.';
    return `<li><strong>${escapeHtml(calendar.name)}</strong><span>${label} · ${detail}</span></li>`;
  }).join('');
  return `<p role="status">${escapeHtml(status.message)}<br>${escapeHtml(attempt)}${attempt ? '<br>' : ''}${success}</p>${error}${conflicts}${calendars ? `<ul class="icloud-sync-calendars" aria-label="Calendar sync status">${calendars}</ul>` : ''}`;
}
async function encryptAccountCredential(value) {
  if (!accountCredentialKey) {
    const status = await rawApi('/api/beta/status');
    if (!status.credential_public_key) throw new Error('Secure credential support is not installed on this local server. Run Install Align Add-ons.bat and choose Owner accounts and remote access.');
    const raw = Uint8Array.from(atob(status.credential_public_key), c => c.charCodeAt(0));
    accountCredentialKey = await crypto.subtle.importKey('spki', raw, {name:'RSA-OAEP', hash:'SHA-256'}, false, ['encrypt']);
  }
  const encrypted = await crypto.subtle.encrypt({name:'RSA-OAEP'}, accountCredentialKey, new TextEncoder().encode(value));
  let text=''; new Uint8Array(encrypted).forEach(byte => text += String.fromCharCode(byte));
  return btoa(text);
}
function renderICloud() {
  const accountSession = Boolean(state.boot?.beta);
  const local = ['127.0.0.1','localhost','[::1]'].includes(location.hostname);
  if (!accountSession && (!isAdmin || !local)) {
    const scheme = location.protocol === 'https:' ? 'https' : 'http';
    return `<section class="card settings-form"><h2>iCloud Calendar</h2><p>Connect securely from the PC Admin page at <strong>${scheme}://127.0.0.1:${location.port || (scheme === 'https' ? '443' : '80')}/admin</strong>, then open the iCloud Calendar tab. Do not enter Apple credentials over the Wi-Fi address.</p><p>Once enabled, Align reads your selected calendars and manages its own shifts in your chosen calendar while the PC is running.</p></section>`;
  }
  const status = cloudState;
  return `<section class="card settings-form"><h2>iCloud Calendar</h2><p class="helper">Optional direct connection. ${accountSession ? 'Your app-specific password is encrypted in this browser before it crosses the public connection and encrypted again while stored on the Align server.' : 'Credentials stay in memory for this server run and are sent only to Apple over HTTPS. Reconnect after restarting Align.'}</p>
    <p class="apply-note">${location.hostname === 'beta.getalign.co.uk' ? 'iCloud support is installed on the hosted server. ' : 'First run <strong>Install Align Add-ons.bat</strong> and choose iCloud calendar support, then restart Align. '}Use an <a href="https://support.apple.com/en-gb/102654" target="_blank" rel="noopener noreferrer">Apple app-specific password</a>, not your main Apple password.</p>
    ${cloudMessage ? `<p role="alert" class="planner-error">${escapeHtml(cloudMessage)}</p>` : ''}
    ${cloudSyncStatusMarkup(status)}
    <button class="small-button" data-cloud-action="status" ${cloudBusy ? 'disabled' : ''}>Check connection</button>
    ${!status?.connected ? `<form data-cloud-form="connect" class="settings-form"><label class="field">Apple Account email<input name="username" type="email" autocomplete="username" required></label><label class="field">App-specific password<input name="password" type="password" autocomplete="off" required></label><p class="helper">Connect only lists calendars. No events are changed until you select calendars and enable sync.</p><button class="primary-button" ${cloudBusy ? 'disabled' : ''}>${cloudBusy ? 'Connecting…' : 'Connect & list calendars'}</button></form>` : status.enabled ? `<div class="button-row"><button class="primary-button" data-cloud-action="sync" ${cloudBusy ? 'disabled' : ''}>Sync now</button><button class="secondary-button" data-cloud-action="disconnect" ${cloudBusy ? 'disabled' : ''}>Disconnect</button></div>` : `<form data-cloud-form="enable" class="settings-form"><label class="field">Calendar for Align shifts<select name="target" required><option value="">Choose a calendar</option>${status.calendars.map(c => `<option value="${c.id}" ${c.id === status.target ? 'selected' : ''}>${escapeHtml(c.name)}</option>`).join('')}</select></label><fieldset class="setup-options"><legend>Read these calendars for clash checking</legend>${status.calendars.map(c => `<label class="setup-check"><input type="checkbox" name="read_ids" value="${c.id}" ${status.read_ids.includes(c.id) ? 'checked' : ''}><span>${escapeHtml(c.name)}</span></label>`).join('')}</fieldset><label class="setup-check"><input type="checkbox" name="consent" required><span>Allow Align to read the selected calendars and add, update or remove its own shift events in the destination calendar.</span></label><button class="primary-button" ${cloudBusy ? 'disabled' : ''}>Enable iCloud sync</button><button type="button" class="text-button" data-cloud-action="disconnect">Cancel connection</button></form>`}
    ${status?.connected ? `<form data-cloud-form="create-calendar" class="settings-form"><h3>Create a new calendar</h3><label class="field">Calendar name<input name="calendar_name" maxlength="80" required placeholder="e.g. Align Personal"></label><p class="helper">Creates a calendar in your connected iCloud account. An existing calendar with the same name is reused.</p><button class="secondary-button" ${cloudBusy?'disabled':''}>Create calendar</button></form><div class="settings-form"><h3>Calendar for each event category</h3><p class="helper">Choose Edit to select an existing calendar. To create one per category, create a calendar with that category’s name above, then select it here.</p>${(state.boot.sections||[]).map(s=>`<p>${escapeHtml(s.name)} · ${escapeHtml(s.calendar_name||'No linked calendar')} <button class="small-button" data-action="edit-section" data-id="${s.id}">Edit</button></p>`).join('')}</div>` : ''}
    <p class="helper">Two-way sync runs about once a minute while Align is running. Align uploads owned shifts and section events; iCloud edits to those same items are pulled back into Align. Clash calendars are read-only. Annual leave continues to use the ICS feed. Leave-at alerts and travel notes are copied into iCloud calendar alerts and event notes.</p><p class="helper">Disconnect keeps the events already written to iCloud, removes the local iCloud clash cache and forgets the login. Do not also subscribe to or import Align’s ICS into the same calendar—you may see duplicates. Phone alerts depend on your calendar settings.</p></section>`;
}
document.addEventListener('submit', async event => {
  const form = event.target;
  if (!form.dataset.cloudForm) return;
  event.preventDefault(); if (cloudBusy) return;
  const kind = form.dataset.cloudForm;
  let body;
  if (kind === 'connect') {
    const username=form.elements.username.value, password=form.elements.password.value;
    if (state.boot?.beta) body={username_box:await encryptAccountCredential(username),password_box:await encryptAccountCredential(password)};
    else body={username,password};
    form.elements.password.value='';
  } else if (kind === 'create-calendar') body={name:form.elements.calendar_name.value};
  else body={target:form.elements.target.value,read_ids:[...form.querySelectorAll('[name=read_ids]:checked')].map(i=>i.value),consent:form.elements.consent.checked};
  const previousAttempt = cloudState?.last_attempt || null;
  cloudBusy = true; cloudMessage = ''; render();
  try {
    cloudState = await api(`/api/icloud/${kind}`,{method:'POST',body});
    await refresh();
    if (kind === 'enable') pollCloudSyncStatus(previousAttempt);
  }
  catch(error) { cloudMessage = error.message; }
  finally { if(body){delete body.password;delete body.password_box;delete body.username_box;} cloudBusy = false; render(); }
});
document.addEventListener('click', async event => {
  const button = event.target.closest('[data-cloud-action]');
  if (!button || cloudBusy) return;
  const action = button.dataset.cloudAction;
  if (action === 'disconnect') clearTimeout(cloudStatusPollTimer);
  const previousAttempt = cloudState?.last_attempt || null;
  cloudBusy = true; cloudMessage = ''; render();
  try {
    cloudState = await api(action === 'status' ? '/api/icloud/manage' : `/api/icloud/${action}`, action === 'status' ? {} : {method:'POST',body:{}});
    if (action === 'sync') pollCloudSyncStatus(previousAttempt);
  }
  catch(error) { cloudMessage = error.message; }
  finally { cloudBusy = false; render(); }
});

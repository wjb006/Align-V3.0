/* Upload a rota, review every row, and approve it into the existing shift planner. */
let workRota = {capabilities: null, current: null, error: '', stage: '', busy: false, editing: null};

const rotaMessages = {
  ocr_unavailable: 'Local photo/scanned-PDF reading is unavailable. Install the Align OCR runtime and try again.',
  multiple_people: 'This file looks like a shared rota. Remove other people and upload only your rows.',
  unrecognized_table: 'No shift rows were found. Empty cells are not treated as days off.',
  date: 'This date could be read in more than one way. Enter it as YYYY-MM-DD.',
  time_gap: 'This time does not exist when the clocks change. Choose another time.',
  time_fold: 'This time happens twice when the clocks change. Confirm it before approving.',
};

function rotaCapabilityNote() {
  const caps = workRota.capabilities || {};
  const sheets = [caps.csv && 'CSV', caps.xlsx && 'Excel', caps.pdf_text && 'text PDFs'].filter(Boolean).join(', ');
  const photo = caps.image_ocr ? (caps.heic_ocr ? 'JPG, PNG and HEIC photos' : 'JPG and PNG photos') : 'photos (local OCR runtime not detected)';
  const scanned = caps.scanned_pdf_ocr ? 'scanned PDFs' : 'scanned PDFs (local PDF OCR runtime not detected)';
  const local = caps.image_ocr ? ' OCR runs locally; rota files are not sent to an external OCR service.' : ' Install the local Align OCR runtime to enable photo and scanned-PDF reading.';
  return `${sheets || 'Supported files'} and ${photo}; ${scanned}.${local}`;
}

async function openWorkRota() {
  const work = (state.sectionDefinitions || []).find(section => section.key === 'work' && section.optional && !section.enabled);
  try {
    if (work) {
      await api(`/api/builder/records/${work.key}/enable`, {method: 'POST', body: {}});
      state.sectionDefinitions = (await api('/api/sections/definitions')).sections || state.sectionDefinitions;
    }
    if (!workRota.capabilities) workRota.capabilities = await api('/api/work/rota/capabilities');
    workRota.error = '';
    state.tab = 'work-rota';
    render();
  } catch (error) {
    toast(error.message);
  }
}

function renderWorkRota() {
  const current = workRota.current;
  const entries = current?.entries || [];
  const note = rotaCapabilityNote();
  return `<section class="page work-rota">
    <div class="add-head"><p class="eyebrow">Work planner</p><h1>Upload my rota</h1>
      <p class="subtle">${escapeHtml(note)}</p></div>
    <section class="card">
      <form data-rota-form="upload">
        <label class="work-rota-drop" for="rota-files">Choose files or drop them here
          <input id="rota-files" name="files" type="file" multiple accept=".csv,.xlsx,.pdf,.jpg,.jpeg,.png,.heic,.heif,image/*,application/pdf,text/csv">
        </label>
        <p class="helper">Nothing is added to the planner until you approve it. The original files are deleted after they are checked.</p>
        <p class="helper" role="status">${escapeHtml(workRota.stage || '')}</p>
        <p role="alert">${escapeHtml(workRota.error || current?.error || '')}</p>
        <button class="primary-button" type="submit" ${workRota.busy ? 'disabled' : ''}>${workRota.busy ? 'Reading rota…' : 'Read rota'}</button>
      </form>
    </section>
    ${current ? renderRotaReview(current, entries) : ''}
  </section>`;
}

function renderRotaReview(current, entries) {
  const summary = current.import || {};
  const notices = (summary.notice_codes || []).map(code => rotaMessages[code] || '').filter(Boolean);
  const warnings = (current.warnings || []).map(item => `${rotaMessages[item.code] || item.code} (${escapeHtml(item.format || 'file')} ${item.index})`);
  const rows = entries.map(renderRotaEntry).join('') || '<p class="helper">No rows to review.</p>';
  return `<section class="card" aria-labelledby="rota-review-title">
    <div class="section-head"><h2 id="rota-review-title">Review</h2><p class="helper">${escapeHtml(summary.status || '')} · ${entries.length} rows</p></div>
    ${notices.map(text => `<p class="helper">${escapeHtml(text)}</p>`).join('')}
    ${warnings.map(text => `<p class="helper">${text}</p>`).join('')}
    <div class="work-rota-list">${rows}</div>
    <div class="button-row">
      <button class="primary-button" type="button" data-rota-action="approve" ${workRota.busy ? 'disabled' : ''}>Approve selected</button>
      <button class="secondary-button" type="button" data-rota-action="undo" ${workRota.busy ? 'disabled' : ''}>Undo imported rows</button>
      <button class="text-button" type="button" data-rota-action="delete" ${workRota.busy ? 'disabled' : ''}>Delete this review</button>
    </div>
  </section>`;
}

function renderRotaEntry(entry) {
  const editing = workRota.editing === entry.id;
  const band = entry.confidence_band || 'low';
  const problem = entry.ambiguity ? (rotaMessages[entry.ambiguity] || 'This row needs a correction.') : '';
  const duplicate = entry.duplicate_shift_id ? 'This shift is already on the planner.' : '';
  const checked = entry.preselected ? 'checked' : '';
  const disabled = entry.approvable && entry.review_status === 'pending' ? '' : 'disabled';
  return `<article class="work-rota-entry work-rota-${escapeHtml(band)}" data-entry-id="${escapeHtml(entry.id)}">
    <label class="setup-check"><input type="checkbox" data-rota-select value="${escapeHtml(entry.id)}" data-revision="${entry.revision}" ${checked} ${disabled}> Include</label>
    <div><strong>${escapeHtml(entry.work_date || entry.source_date_text || 'Date needed')}</strong>
      <span>${escapeHtml(entry.start_time || '—')}–${escapeHtml(entry.end_time || '—')}</span></div>
    <p>${escapeHtml(entry.shift_label || entry.department || 'Shift')} · ${escapeHtml(entry.location_text || 'Location needed')} · ${escapeHtml(entry.entry_kind)}</p>
    <p class="helper">${escapeHtml(band)} confidence${entry.review_status === 'imported' ? ' · imported' : ''}${entry.review_status === 'rejected' ? ' · rejected' : ''}</p>
    ${problem ? `<p role="status">${escapeHtml(problem)}</p>` : ''}
    ${duplicate ? `<p role="status">${escapeHtml(duplicate)}</p>` : ''}
    <div class="button-row">
      <button type="button" class="small-button" data-rota-action="edit" data-id="${escapeHtml(entry.id)}">Edit</button>
      <button type="button" class="small-button" data-rota-action="reject" data-id="${escapeHtml(entry.id)}" data-revision="${entry.revision}">Reject</button>
    </div>
    ${editing ? renderRotaEditor(entry) : ''}
  </article>`;
}

function renderRotaEditor(entry) {
  const current = workRota.current || {};
  const locationOptions = (current.locations || []).map(item => `<option value="${item.id}" ${Number(item.id) === Number(entry.location_id) ? 'selected' : ''}>${escapeHtml(item.name)}</option>`).join('');
  const typeOptions = (current.shift_types || []).map(item => `<option value="${item.id}" ${Number(item.id) === Number(entry.shift_type_id) ? 'selected' : ''}>${escapeHtml(item.name)}</option>`).join('');
  const kinds = ['shift', 'day_off', 'leave', 'sickness', 'unknown'].map(kind => `<option value="${kind}" ${entry.entry_kind === kind ? 'selected' : ''}>${kind.replace('_', ' ')}</option>`).join('');
  return `<form class="settings-form" data-rota-form="edit" data-id="${escapeHtml(entry.id)}" data-revision="${entry.revision}">
    <div class="form-grid two">
      <label class="field">Date<input name="work_date" type="date" value="${escapeHtml(entry.work_date || '')}" required></label>
      <label class="field">Kind<select name="entry_kind">${kinds}</select></label>
      <label class="field">Start<input name="start_time" type="time" value="${escapeHtml(entry.start_time || '')}"></label>
      <label class="field">End<input name="end_time" type="time" value="${escapeHtml(entry.end_time || '')}"></label>
      <label class="field">Label<input name="shift_label" value="${escapeHtml(entry.shift_label || '')}" maxlength="80"></label>
      <label class="field">Department<input name="department" value="${escapeHtml(entry.department || '')}" maxlength="80"></label>
      <label class="field">Location<select name="location_id"><option value="">Not matched</option>${locationOptions}</select></label>
      <label class="field">Shift area<select name="shift_type_id"><option value="">Not matched</option>${typeOptions}</select></label>
    </div>
    <label class="setup-check"><input name="confirm_ambiguity" type="checkbox"> Use this clock time even if it occurs twice when the clocks change</label>
    <div class="button-row"><button class="primary-button" type="submit">Save correction</button><button class="text-button" type="button" data-rota-action="cancel-edit">Cancel</button></div>
  </form>`;
}

function rotaFilesFrom(form) {
  const input = form.querySelector('input[type=file]');
  return input?.files ? [...input.files] : [];
}

async function uploadRotaFiles(fileList) {
  if (!fileList.length) throw new Error('Choose at least one file.');
  const body = new FormData();
  fileList.forEach(file => body.append('files', file, file.name));
  workRota.busy = true;
  workRota.stage = 'Checking files';
  workRota.error = '';
  render();
  workRota.stage = 'Reading rota';
  const response = await fetch('/api/work/rota/imports', {method: 'POST', body});
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || 'The rota could not be read.');
  workRota.current = payload;
  workRota.error = payload.status === 'failed' || payload.import?.status === 'failed' ? (payload.error || 'This rota could not be read.') : '';
  workRota.stage = payload.import?.status === 'review' ? 'Ready to review' : '';
}

async function refreshRota(importId) {
  workRota.current = await api(`/api/work/rota/imports/${importId}`);
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!form.dataset.rotaForm) return;
  event.preventDefault();
  try {
    if (form.dataset.rotaForm === 'upload') {
      await uploadRotaFiles(rotaFilesFrom(form));
    } else {
      const entry = (workRota.current?.entries || []).find(item => item.id === form.dataset.id);
      const values = Object.fromEntries(new FormData(form));
      const saved = await api(`/api/work/rota/imports/${workRota.current.import.id}/entries/${form.dataset.id}`, {
        method: 'PATCH',
        body: {
          revision: Number(form.dataset.revision),
          work_date: values.work_date,
          start_time: values.start_time,
          end_time: values.end_time,
          shift_label: values.shift_label,
          department: values.department,
          entry_kind: values.entry_kind,
          location_id: values.location_id ? Number(values.location_id) : null,
          shift_type_id: values.shift_type_id ? Number(values.shift_type_id) : null,
          confirm_ambiguity: Boolean(form.elements.confirm_ambiguity.checked),
          review_status: entry?.review_status === 'rejected' ? 'pending' : 'pending',
        },
      });
      workRota.editing = null;
      const entries = workRota.current.entries.map(item => item.id === saved.entry.id ? saved.entry : item);
      workRota.current = {...workRota.current, entries};
    }
  } catch (error) {
    workRota.error = error.message;
    toast(error.message);
  } finally {
    workRota.busy = false;
    if (state.tab === 'work-rota') render();
  }
});

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-rota-action]');
  if (!button || state.tab !== 'work-rota' || !workRota.current) return;
  const action = button.dataset.rotaAction;
  const importId = workRota.current.import.id;
  try {
    if (action === 'edit') { workRota.editing = button.dataset.id; render(); return; }
    if (action === 'cancel-edit') { workRota.editing = null; render(); return; }
    if (action === 'reject') {
      const saved = await api(`/api/work/rota/imports/${importId}/entries/${button.dataset.id}`, {method: 'PATCH', body: {revision: Number(button.dataset.revision), review_status: 'rejected'}});
      workRota.current.entries = workRota.current.entries.map(item => item.id === saved.entry.id ? saved.entry : item);
    }
    if (action === 'approve') {
      const chosen = [...document.querySelectorAll('[data-rota-select]:checked')].map(input => ({id: input.value, revision: Number(input.dataset.revision)}));
      if (!chosen.length) throw new Error('Choose at least one row to approve.');
      workRota.busy = true;
      render();
      const result = await api(`/api/work/rota/imports/${importId}/approve`, {method: 'POST', body: {idempotency_key: crypto.randomUUID(), entries: chosen}});
      await refreshRota(importId);
      const conflicts = (result.conflicts || []).map(item => item.message).filter(Boolean);
      workRota.error = conflicts.join(' ');
      if (result.created?.length) toast('Approved rows are now in the planner.');
    }
    if (action === 'undo') {
      workRota.busy = true;
      render();
      const result = await api(`/api/work/rota/imports/${importId}/undo`, {method: 'POST', body: {}});
      await refreshRota(importId);
      const conflicts = (result.conflicts || []).map(item => item.message).filter(Boolean);
      workRota.error = conflicts.join(' ');
    }
    if (action === 'delete') {
      await api(`/api/work/rota/imports/${importId}`, {method: 'DELETE'});
      workRota.current = null;
      workRota.editing = null;
      workRota.error = '';
    }
  } catch (error) {
    workRota.error = error.message;
    toast(error.message);
  } finally {
    workRota.busy = false;
    if (state.tab === 'work-rota') render();
  }
});

document.addEventListener('dragover', event => {
  if (!event.target.closest('.work-rota-drop')) return;
  event.preventDefault();
});
document.addEventListener('drop', event => {
  const zone = event.target.closest('.work-rota-drop');
  if (!zone) return;
  event.preventDefault();
  const input = zone.querySelector('input[type=file]');
  try {
    if (input && event.dataTransfer?.files?.length) input.files = event.dataTransfer.files;
  } catch (_) { /* Some browsers keep the file input read-only; the picker still works. */ }
});
document.addEventListener('keydown', event => {
  const zone = event.target.closest?.('.work-rota-drop');
  if (!zone || !['Enter', ' '].includes(event.key)) return;
  event.preventDefault();
  zone.querySelector('input[type=file]')?.click();
});

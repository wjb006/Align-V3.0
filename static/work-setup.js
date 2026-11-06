/* V3 Work records are managed through the shared, account-private Builder API.
   The retired /api/work-setup endpoint is intentionally not called here. */
async function openWorkSetup() {
  if (typeof builderOpenLayout !== 'function') {
    toast('Work records are not available. Refresh Align and try again.');
    return;
  }
  await builderOpenLayout('work');
}

function renderWorkSetup() {
  return `<section class="page work-settings">
    <div class="add-head"><p class="eyebrow">Work planner</p><h1>Work details</h1>
      <p class="subtle">Start with your rota, or add an individual work record. Workplaces and shift areas can be saved as you use them.</p></div>
    <section class="card settings-form">
      <button class="primary-button" data-action="work-rota">Upload my rota</button>
      <p class="helper">Photos, scanned PDFs, Excel and CSV are supported when the local OCR runtime is available. Nothing reaches your planner until you review and approve it.</p>
      <button class="secondary-button" data-action="work-setup">Manage work records</button>
    </section>
  </section>`;
}

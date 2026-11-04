/* Finance ledger. Figures live in finance.db, not the planner database. */
let financeState = {data: null, error: '', loading: false};

function financeMoney(pence) {
  const value = Number(pence || 0);
  const sign = value < 0 ? '-' : '';
  return `${sign}£${(Math.abs(value) / 100).toFixed(2)}`;
}

async function openFinance() {
  state.tab = 'finance';
  financeState.loading = true;
  financeState.error = '';
  render();
  try {
    financeState.data = await api('/api/finance');
  } catch (error) {
    financeState.error = error.message;
  } finally {
    financeState.loading = false;
    if (state.tab === 'finance') render();
  }
}

function renderFinanceLedger() {
  const data = financeState.data;
  if (!data && financeState.loading) return '<section class="page finance-page"><p class="empty" role="status">Loading finance…</p></section>';
  if (!data) return `<section class="page finance-page"><div class="card" role="alert">${escapeHtml(financeState.error || 'Finance could not be opened.')}</div></section>`;
  const reminders = (data.reminders || []).map(item => `<li>${escapeHtml(item.message)} ${item.payee ? escapeHtml(item.payee) + ' · ' : ''}${financeMoney(item.amount_pence)}</li>`).join('');
  const categories = (data.categories || []).map(item => `<li>${escapeHtml(item.category)} · ${item.direction === 'in' ? 'In' : 'Out'} ${financeMoney(item.total_pence)}</li>`).join('');
  const flow = (data.cash_flow || []).slice(0, 8).map(item => `<li>${escapeHtml(item.date)} · ${escapeHtml(item.label)} · ${item.direction === 'in' ? 'In' : 'Out'} ${financeMoney(item.amount_pence)}</li>`).join('');
  const rows = (data.entries || []).map(entry => `<article class="finance-row"><div><strong>${escapeHtml(entry.booked_on)}</strong> ${escapeHtml(entry.payee || entry.category || entry.entry_kind)}<p class="helper">${escapeHtml(entry.entry_kind.replace('_', ' '))} · ${entry.direction === 'in' ? 'In' : 'Out'} ${financeMoney(entry.amount_pence)}${entry.recurring ? ' · Repeats monthly' : ''}</p></div><button class="text-button" type="button" data-finance-action="delete" data-id="${escapeHtml(entry.id)}">Delete</button></article>`).join('');
  const bills = (data.entries || []).filter(entry => entry.entry_kind === 'bill');
  return `<section class="page finance-page">
    <div class="add-head"><p class="eyebrow">Finance</p><h1>Money in and out</h1>
      <p class="subtle">This ledger is kept in its own finance file, separate from your planner. Card numbers and passwords are not stored.</p></div>
    <div class="finance-stats">
      <article class="card"><span>Balance</span><strong>${financeMoney(data.balance_pence)}</strong></article>
      <article class="card"><span>In this month</span><strong>${financeMoney(data.month.in_pence)}</strong></article>
      <article class="card"><span>Out this month</span><strong>${financeMoney(data.month.out_pence)}</strong></article>
    </div>
    <section class="card"><h2>Reminders</h2>${reminders ? `<ul>${reminders}</ul>` : '<p class="helper">No due bills, missing income, or low-balance warning.</p>'}</section>
    <section class="card"><h2>This month by category</h2>${categories ? `<ul>${categories}</ul>` : '<p class="helper">No transactions this month yet.</p>'}</section>
    <section class="card"><h2>Upcoming cash flow</h2>${flow ? `<ul>${flow}</ul>` : '<p class="helper">Nothing expected in the next two months.</p>'}</section>
    <form class="card settings-form" data-finance-form="entry">
      <h2>Add an entry</h2>
      <div class="form-grid two">
        <label class="field">Kind<select name="entry_kind"><option value="transaction">Transaction</option><option value="bill">Bill</option><option value="expected_income">Expected income</option></select></label>
        <label class="field">Direction<select name="direction"><option value="out">Out</option><option value="in">In</option></select></label>
        <label class="field">Date<input name="booked_on" type="date" required value="${new Date().toISOString().slice(0, 10)}"></label>
        <label class="field">Amount<input name="amount" inputmode="decimal" placeholder="0.00" required></label>
        <label class="field">Category<input name="category" maxlength="40"></label>
        <label class="field">Source or payee<input name="payee" maxlength="80"></label>
        <label class="field">Account note<input name="account_note" maxlength="80" placeholder="A name, not a card number"></label>
        <label class="field">Pays bill<select name="bill_id"><option value="">None</option>${bills.map(bill => `<option value="${bill.id}">${escapeHtml(bill.booked_on)} · ${escapeHtml(bill.payee || bill.category || 'Bill')}</option>`).join('')}</select></label>
      </div>
      <label class="field">Notes<textarea name="notes" maxlength="200" rows="2"></textarea></label>
      <label class="setup-check"><input name="recurring" type="checkbox"> Repeats monthly</label>
      <button class="primary-button" type="submit">Save entry</button>
    </form>
    <form class="card settings-form" data-finance-form="import">
      <h2>Import a bank statement</h2>
      <p class="helper">CSV with a header row: date, amount, direction, category, payee, account, notes. A negative amount is money out.</p>
      <label class="field">Statement<input name="statement" type="file" accept=".csv,text/csv" required></label>
      <button class="secondary-button" type="submit">Import CSV</button>
    </form>
    <section class="card"><h2>Ledger</h2>${rows || '<p class="helper">No entries yet.</p>'}</section>
    ${financeState.error ? `<p role="alert">${escapeHtml(financeState.error)}</p>` : ''}
  </section>`;
}

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!form.dataset.financeForm) return;
  event.preventDefault();
  try {
    if (form.dataset.financeForm === 'import') {
      const file = form.statement.files[0];
      if (!file) throw new Error('Choose a CSV file first.');
      const csv = await file.text();
      financeState.data = (await api('/api/finance/import', {method: 'POST', body: {csv}})).summary;
    } else {
      const values = Object.fromEntries(new FormData(form));
      await api('/api/finance/entries', {method: 'POST', body: {
        entry_kind: values.entry_kind,
        direction: values.direction,
        booked_on: values.booked_on,
        amount: values.amount,
        category: values.category,
        payee: values.payee,
        account_note: values.account_note,
        notes: values.notes,
        recurring: Boolean(form.elements.recurring.checked),
        bill_id: values.bill_id ? Number(values.bill_id) : null,
      }});
      financeState.data = await api('/api/finance');
    }
    financeState.error = '';
    toast('Finance entry saved.');
  } catch (error) {
    financeState.error = error.message;
    toast(error.message);
  }
  if (state.tab === 'finance') render();
});

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-finance-action="delete"]');
  if (!button) return;
  try {
    await api(`/api/finance/entries/${button.dataset.id}`, {method: 'DELETE'});
    financeState.data = await api('/api/finance');
    financeState.error = '';
  } catch (error) {
    financeState.error = error.message;
    toast(error.message);
  }
  if (state.tab === 'finance') render();
});

function scheduleViewSwitch() {
  return `<div class="schedule-view-switch" role="group" aria-label="Schedule view"><button data-month-action="list" aria-pressed="${state.scheduleView === 'list'}">List</button><button data-month-action="week" aria-pressed="${state.scheduleView === 'week'}">Week</button><button data-month-action="month" aria-pressed="${state.scheduleView === 'month'}">Month</button></div>`;
}
function offsetMonth(month, offset) {
  const value = fromIso(`${month}-01`); value.setMonth(value.getMonth() + offset);
  return toIso(value).slice(0,7);
}
async function loadScheduleMonth(month, view = 'month') {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) return;
  const request = ++scheduleRequest;
  state.scheduleView = view; state.scheduleMonth = month;
  state.scheduleFocus = month === isoToday().slice(0,7) ? isoToday() : `${month}-01`; state.scheduleLoading = true; state.scheduleError = ''; render();
  try {
    const result = await api(`/api/month?month=${month}`);
    if (request === scheduleRequest) state.monthData = result;
  } catch (error) { if (request === scheduleRequest) state.scheduleError = error.message; }
  finally { if (request === scheduleRequest) { state.scheduleLoading = false; if (['calendar','planner'].includes(state.tab)) render(); } }
}
function renderPlannerList(data, label, days) {
  const rows = days.map(day => {
    const events = weekEventsForDay(data, day);
    if (!events.length) return '';
    const heading = prettyDate(day, {weekday:'long',day:'numeric',month:'long'});
    return `<section class="planner-list-day ${day === isoToday() ? 'is-today' : ''}"><h3>${escapeHtml(heading)}${day === isoToday() ? '<span>Today</span>' : ''}</h3><div class="planner-list-items">${weekEventRows(data, day)}</div></section>`;
  }).join('');
  return rows ? `<div class="planner-list" aria-label="${escapeHtml(label)} agenda">${rows}</div>` : `<div class="card empty">Nothing planned in ${escapeHtml(label)}.</div>`;
}
function renderMonthCalendar() {
  const data = state.monthData?.month === state.scheduleMonth ? state.monthData : null;
  const label = prettyDate(`${state.scheduleMonth}-01`, {month:'long',year:'numeric'});
  let days = [];
  if (data) for (let day = data.start; day <= data.end; day = addDays(day,1)) days.push(day);
  return `<section class="page"><div class="add-head"><p class="eyebrow">Your calendar</p><h1>Calendar</h1><p class="subtle">See your events by date. Choose a view that suits you.</p></div>${scheduleViewSwitch()}
    <div class="schedule-week-nav"><button class="secondary-button" data-month-action="prev" aria-label="Previous month">‹</button><h2>${escapeHtml(label)}</h2><button class="secondary-button" data-month-action="next" aria-label="Next month">›</button></div>
    <div class="schedule-week-tools"><label class="field">Go to month<input type="month" data-schedule-month value="${state.scheduleMonth}"></label><button class="small-button" data-month-action="today">This month</button></div>
    ${state.scheduleError ? `<div class="planner-error" role="alert">${escapeHtml(state.scheduleError)}<button class="small-button" data-month-action="retry">Retry</button></div>` : state.scheduleLoading ? '<p class="empty" role="status">Loading month…</p>' : data ? `${state.scheduleView === 'list' ? renderPlannerList(data, label, days.filter(day => day.startsWith(state.scheduleMonth))) : `
      <div class="month-grid" aria-label="${escapeHtml(label)} calendar"><div class="month-weekdays">${WEEK_DAYS.map(d => `<span>${d.slice(0,3)}</span>`).join('')}</div><div class="month-days">${days.map(day => {
        const events = weekEventsForDay(data, day);
        const full = `${prettyDate(day,{weekday:'long',day:'numeric',month:'long',year:'numeric'})}. ${events.map(e => e.title).join('; ') || 'No events'}.`;
        return `<button class="month-day ${day.startsWith(state.scheduleMonth) ? '' : 'outside-month'} ${day === isoToday() ? 'is-today' : ''}" data-month-action="day" data-date="${day}" aria-label="${escapeHtml(full)}" ${day === isoToday() ? 'aria-current="date"' : ''}><span class="month-date-row"><span class="month-date">${Number(day.slice(-2))}</span>${day === isoToday() ? '<span class="month-today-label">Today</span>' : ''}</span>
          ${events.map(e => `<span class="month-event" style="--section-colour:${safeColour(e.section_colour)}"><strong>${e.all_day ? 'All day' : escapeHtml(e.start_at.slice(11,16))}</strong> ${escapeHtml(e.title)}</span>`).join('')}
          ${!events.length ? '<span class="month-rest">No events</span>' : ''}</button>`;
      }).join('')}</div></div><p class="helper">Tap any date to see that week’s events.</p>`}` : '<p class="empty">Choose a month to load your calendar.</p>'}
      </section>`;
}
document.addEventListener('click', async event => {
  const el = event.target.closest('[data-month-action]');
  if (!el) return;
  const action = el.dataset.monthAction;
  if (action === 'week') { if (state.scheduleView !== 'week') await loadScheduleWeek(state.scheduleFocus); return; }
  if (action === 'month') { if (state.scheduleView !== 'month') await loadScheduleMonth(state.scheduleFocus.slice(0,7)); return; }
  if (action === 'list') { if (state.scheduleView !== 'list') await loadScheduleMonth(state.scheduleFocus.slice(0,7), 'list'); return; }
  if (action === 'day') { await loadScheduleWeek(el.dataset.date); return; }
  await loadScheduleMonth(action === 'prev' ? offsetMonth(state.scheduleMonth,-1) : action === 'next' ? offsetMonth(state.scheduleMonth,1) : action === 'today' ? isoToday().slice(0,7) : state.scheduleMonth, state.scheduleView);
});
document.addEventListener('change', event => {
  if (event.target.hasAttribute('data-schedule-month') && event.target.value) void loadScheduleMonth(event.target.value, state.scheduleView);
});

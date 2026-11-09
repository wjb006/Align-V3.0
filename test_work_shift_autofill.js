const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const source = fs.readFileSync('static/shift-planner.js', 'utf8')
  .replace('  function pmShiftMarkup(', '  window.testPm = {matchingPmPattern, autofillPmPattern, firstEmptyShiftWeek};\n  function pmShiftMarkup(');
const listeners = {};
const am = {id: 1, active: 1, location_id: 1, shift_type_id: 1, label: 'AM', start_time: '08:30', end_time: '12:30', applicable_days: '[]'};
const pm = {id: 2, active: 1, location_id: 1, shift_type_id: 2, label: 'PM', start_time: '13:00', end_time: '17:30', break_minutes: 10, applicable_days: '["Monday","Tuesday"]'};
const otherAm = {...am, id: 3, location_id: 2, shift_type_id: 3};
const otherPm = {...pm, id: 6, location_id: 2, shift_type_id: 4};
const state = {shiftPlannerData: {templates: [am, pm, otherAm, otherPm], shifts: [], locations: [{id: 1, name: 'Arrowe Park'}, {id: 2, name: 'Other'}], shift_types: [{id: 1, name: 'Clinic'}, {id: 2, name: 'Hub'}, {id: 3, name: 'Other AM'}, {id: 4, name: 'Other PM'}]}};
const context = {state, window: {}, document: {addEventListener: (name, fn) => {(listeners[name] ||= []).push(fn);}, querySelector: () => null}, console,
  FormData: class {constructor(form) {this.form = form;} entries() {return Object.entries(this.form.elements).filter(([, field]) => !field.disabled && (field.checked === undefined || field.checked)).map(([name, field]) => [name, field.value]);}}};
vm.createContext(context);
vm.runInContext(source, context);
async function dispatch(name, event) {
  for (const listener of listeners[name] || []) await listener(event);
}

function form() {
  const field = value => ({value, disabled: false});
  const elements = {
    template_id: field('1'), location_id: field('1'), shift_type_id: field('1'),
    start_time: field('08:30'), end_time: field('12:30'),
    pm_shift_type_id: field(''), pm_template_id: field(''),
    pm_start_time: field('13:00'), pm_end_time: field('17:00'), pm_break_minutes: field('0')
  };
  const toggle = {checked: false, disabled: false, value: '1'};
  elements.add_pm_shift = toggle;
  elements.break_minutes = field('0');
  elements.notes = field('');
  const panel = {hidden: true, querySelectorAll: () => [elements.pm_shift_type_id, elements.pm_template_id, elements.pm_start_time, elements.pm_end_time, elements.pm_break_minutes]};
  const selectors = {'[data-add-pm-shift]': toggle, '[data-pm-shift-fields]': panel,
    '[data-pm-shift-type]': elements.pm_shift_type_id, '[data-pm-template]': elements.pm_template_id};
  const f = {dataset: {shiftForm: 'shift'}, elements, toggle, panel, days: ['2026-11-09'],
    querySelector: selector => selectors[selector] || elements[(selector.match(/^\[name="(.+)"\]$/)||[])[1]] || null};
  f.closest = () => f;
  return f;
}

function makeForm() {
  const f = form();
  f.querySelectorAll = selector => selector === '[name="selected_days"]:checked' ? f.days.map(value => ({value})) : [];
  return f;
}
const {matchingPmPattern, autofillPmPattern, firstEmptyShiftWeek} = context.window.testPm;
let f = makeForm();
autofillPmPattern(f);
assert.equal(f.toggle.checked, true);
assert.equal(f.panel.hidden, false);
assert.equal(f.elements.pm_template_id.value, '2');
assert.equal(f.elements.pm_shift_type_id.value, '2');
assert.equal(f.elements.pm_start_time.value, '13:00');
assert.equal(f.elements.pm_end_time.value, '17:30');
assert.equal(f.elements.pm_break_minutes.value, 10);

f.elements.end_time.value = '12:00';
autofillPmPattern(f);
assert.equal(f.toggle.checked, false, 'A stale automatic match is removed');
assert.equal(f.panel.hidden, true);
f.elements.end_time.value = '12:30';
autofillPmPattern(f);
const edited = {closest: () => f, matches: selector => selector.includes('[name="pm_end_time"]')};
void dispatch('input', {target: edited});
f.elements.pm_end_time.value = '16:45';
f.elements.end_time.value = '12:00';
autofillPmPattern(f);
assert.equal(f.elements.pm_end_time.value, '16:45', 'Manual PM edits are not replaced');
assert.equal(f.toggle.checked, true);

f = makeForm();
assert.equal(matchingPmPattern(f).id, 2, 'The PM area may differ at the same workplace');
state.shiftPlannerData.templates.push({...pm, id: 5, location_id: 2});
assert.equal(matchingPmPattern(f).id, 2, 'A different workplace is not an automatic match');
state.shiftPlannerData.templates.push({...pm, id: 4});
autofillPmPattern(f);
assert.equal(f.toggle.checked, false, 'Ambiguous matches remain a manual choice');
state.shiftPlannerData.templates.pop();
state.shiftPlannerData.templates.pop();
state.shiftPlannerData.shifts = [{work_date: '2026-11-09', start_time: '14:00'}];
assert.equal(matchingPmPattern(f), null, 'Existing PM shifts are not replaced');
state.shiftPlannerData.shifts = [];
f.days.push('2026-11-11');
assert.equal(matchingPmPattern(f), null, 'The PM pattern must apply to every selected weekday');
f.days = ['2026-11-14'];
assert.equal(matchingPmPattern(f), null, 'Weekend-only shifts do not gain a PM shift');
f.days = ['2026-11-09', '2026-11-14'];
assert.equal(matchingPmPattern(f).id, 2, 'Weekend rules do not block weekday matches');
f.dataset.id = '11';
autofillPmPattern(f);
assert.equal(f.toggle.checked, false, 'Existing shift edits are not changed');
assert.equal(firstEmptyShiftWeek('2026-11-09', [{work_date: '2026-11-10'}, {work_date: '2026-11-22'}, {work_date: '2026-12-01'}]), '2026-11-23');
assert.equal(firstEmptyShiftWeek('2026-11-23', [{work_date: '2026-11-10'}]), '2026-11-23');

(async () => {
  f = makeForm();
  f.dataset.pmManual = '1';
  f.dataset.pmAuto = '1';
  f.elements.location_id.value = '2';
  const locationSelection = {value: '2', closest: () => f, matches: selector => selector === '[name="location_id"]'};
  await dispatch('change', {target: locationSelection});
  assert.equal(f.dataset.pmManual, undefined, 'Changing workplace clears manual PM state');
  assert.equal(f.dataset.pmAuto, undefined, 'Changing workplace clears automatic PM state');
  f.elements.shift_type_id.value = '3';
  const otherAmSelection = {value: '3', closest: () => f, matches: selector => selector === '[name="shift_type_id"]'};
  await dispatch('change', {target: otherAmSelection});
  assert(f.elements.pm_shift_type_id.innerHTML.includes('value="4"'), 'The new workplace PM shift types are rebuilt');
  assert(f.elements.pm_template_id.innerHTML.includes('value="6"'), 'The new workplace PM patterns are rebuilt');

  f = makeForm();
  f.days = ['2026-11-13'];
  pm.applicable_days = '["Friday"]';
  const amSelection = {value: '1', closest: () => f, matches: selector => selector === '[name="template_id"]'};
  await dispatch('change', {target: amSelection});
  assert.equal(f.elements.pm_template_id.value, '2', 'Choosing the AM pattern triggers autofill');
  f.elements.template_id.value = '';
  await dispatch('change', {target: {...amSelection, value: ''}});
  assert.equal(f.toggle.checked, false, 'Clearing the AM pattern removes the automatic PM shift');
  assert.equal(f.panel.hidden, true, 'Clearing the AM pattern hides the automatic PM fields');
  assert.equal(f.elements.pm_template_id.value, '', 'Clearing the AM pattern clears the automatic PM pattern');
  assert(f.panel.querySelectorAll().every(field => field.disabled), 'Automatic PM fields are disabled');
  f.elements.template_id.value = '1';
  await dispatch('change', {target: amSelection});
  f.dataset.pmManual = '1';
  f.elements.pm_end_time.value = '16:45';
  f.elements.template_id.value = '';
  await dispatch('change', {target: {...amSelection, value: ''}});
  assert.equal(f.toggle.checked, true, 'Clearing the AM pattern preserves a manually edited PM shift');
  assert.equal(f.elements.pm_end_time.value, '16:45');
  delete f.dataset.pmManual;
  f.elements.template_id.value = '1';
  await dispatch('change', {target: amSelection});
  f.days.push('2026-11-09');
  const daySelection = {closest: () => f, matches: selector => selector === '[name="selected_days"]'};
  await dispatch('change', {target: daySelection});
  assert.equal(f.elements.template_id.value, '1', 'Changing days retains the selected AM pattern');
  assert.equal(f.toggle.checked, false, 'A pattern not valid on every weekday is no longer autofilled');
  f.days.pop();
  await dispatch('change', {target: daySelection});
  assert.equal(f.toggle.checked, true);
  await dispatch('submit', {target: f, preventDefault() {}});
  assert.equal(state.shiftPlannerReview.shifts.length, 2);
  assert.equal(state.shiftPlannerReview.shifts[1].start_time, '13:00');
  assert.equal(state.shiftPlannerReview.shifts[1].end_time, '17:00', 'Friday finish rule applies to the reviewed PM shift');
  assert.equal(state.shiftPlannerReview.shifts[1].template_id, '2');
  state.plannerAnchor = '2040-01-02';
  state.plannerMode = 'month';
  state.shiftPlannerData.shifts = [];
  const occupied = [{work_date: '2040-01-02'}, {work_date: '2040-01-09'}];
  const initial = firstEmptyShiftWeek('2040-01-02', occupied);
  context.api = async path => path === '/api/shifts' ? {shifts: occupied} : {...state.shiftPlannerData, shifts: []};
  const click = action => dispatch('click', {target: {closest: () => ({dataset: {shiftAction: action}})}, preventDefault() {}});
  await click('add');
  assert.equal(state.plannerAnchor, initial, 'Add shifts opens the first empty week');
  assert.equal(state.plannerMode, 'week');
  assert.equal(state.shiftPlannerModal, 'add');
  await click('previous');
  assert.notEqual(state.plannerAnchor, initial, 'Users can navigate back to a filled week');
  assert.equal(state.shiftPlannerModal, 'add');
  let opened = 0;
  context.openWorkRota = async () => {opened++;};
  context.window.confirm = () => false;
  await click('upload-rota');
  assert.equal(opened, 0, 'Cancelling preserves the manual form');
  context.window.confirm = () => true;
  await click('upload-rota');
  assert.equal(opened, 1, 'The upload action opens the existing rota reader');
  console.log('Work shift PM autofill and empty-week selection passed');
})().catch(error => {console.error(error); process.exitCode = 1;});

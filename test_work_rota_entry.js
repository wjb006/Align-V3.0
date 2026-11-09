const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const listeners = {};
const state = {tab: 'work-rota', shiftPlannerData: {old: true}, shiftPlannerDateShifts: {old: true}};
const calls = [];
const context = {
  state, console, crypto: {randomUUID: () => 'request'},
  document: {
    addEventListener: (name, fn) => {(listeners[name] ||= []).push(fn);},
    querySelectorAll: () => [{value: 'entry', dataset: {revision: '1'}}]
  },
  api: async (url, options) => {
    calls.push([url, options]);
    if (url.endsWith('/approve')) return {created: [1], conflicts: []};
    if (url.endsWith('/undo')) return {conflicts: []};
    return {import: {id: 'import'}, entries: []};
  },
  render: () => {}, toast: () => {}
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/work-rota.js', 'utf8'), context);
vm.runInContext("workRota.current = {import: {id: 'import'}, entries: []}", context);

async function click(action) {
  const event = {target: {closest: () => ({dataset: {rotaAction: action}})}};
  for (const listener of listeners.click) await listener(event);
}
(async () => {
  await click('approve');
  assert(calls.some(([url]) => url.endsWith('/approve')), 'Approval uses the existing import endpoint');
  assert.equal(state.shiftPlannerData, null, 'Approval refreshes planner data on return');
  assert.equal(state.shiftPlannerDateShifts, null);
  state.shiftPlannerData = {old: true};
  state.shiftPlannerDateShifts = {old: true};
  await click('undo');
  assert.equal(state.shiftPlannerData, null, 'Undo refreshes planner data on return');
  assert.equal(state.shiftPlannerDateShifts, null);
  console.log('Rota approval and planner refresh passed');
})().catch(error => {console.error(error); process.exitCode = 1;});

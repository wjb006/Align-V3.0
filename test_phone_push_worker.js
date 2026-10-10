const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const handlers = {}, shown = [];
const context = {
  self: {addEventListener: (name, fn) => {handlers[name] = fn;}, location: {origin: 'https://beta.getalign.co.uk'},
    registration: {showNotification: async (title, options) => {shown.push({title, options});}}},
  URL, console, setTimeout, clearTimeout, AbortController,
};
vm.runInNewContext(fs.readFileSync('static/service-worker.js', 'utf8'), context);
async function push(data) {
  let pending;
  handlers.push({data, waitUntil: p => {pending = p;}});
  await pending;
}
(async () => {
  await push({json: () => ({title: 'private medical detail', body: 'private prescription', tag: 'align-123'})});
  assert.equal(shown[0].title, 'Align');
  assert.equal(shown[0].options.body, 'You have a reminder. Open Align to see the details.');
  assert.equal(shown[0].options.data.url, '/#home');
  await push({json: () => {throw Error('malformed');}});
  assert.equal(shown.length, 2);
  await push({json: () => ({tag: 'align-test'})});
  assert.equal(shown[2].options.body, 'Phone notifications are connected.');
  console.log('PASS: background push, private text, malformed payload fallback and test notification');
})().catch(error => {console.error(error); process.exitCode = 1;});

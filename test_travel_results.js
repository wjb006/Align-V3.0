const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('static/travel-assets.js', 'utf8');
const context = {
  state: { boot: { builder: { document: { travel_results: {} } } } },
  escapeHtml: value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char])),
  journeyBreakdown: () => '<div class="breakdown">steps</div>',
  api: async () => ({}),
  toast: () => {},
  rawApi: async () => ({}),
  document: { addEventListener: () => {}, querySelector: () => null },
  setInterval, clearInterval, queueMicrotask,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/dates.js', 'utf8'), context);
vm.runInContext(source, context);

const journey = (label, departure) => ({
  badges: [label], departure, arrival: '2030-01-01T09:00:00+00:00',
  duration: 40, walking: 8, changes: 1, provider: 'Test OTP', legs: [],
});
const result = { state: 'on_time', journeys: [
  journey('Recommended', '2030-01-01T08:20:00+00:00'),
  journey('Fastest', '2030-01-01T08:30:00+00:00'),
] };

let html = context.travelResult150(result);
if ((html.match(/travel-result-best/g) || []).length !== 1) throw new Error('Default output must mark one best journey card');
if (!html.includes('Show more journeys (1)') || !html.includes('class="travel-alternatives" hidden')) throw new Error('Default output must include collapsed alternatives');

context.state.boot.builder.document.travel_results = { show_best_only: false, show_more: true, visibility: {} };
html = context.travelResult150(result);
if ((html.match(/travel-result-card/g) || []).length !== 2) throw new Error('Expanded configuration must render all journey cards');
if (html.includes('Show more journeys')) throw new Error('Expanded configuration must not render the alternatives control');

context.state.boot.builder.document.travel_results = { show_best_only: true, show_more: true, visibility: { departure_arrival: false } };
html = context.travelResult150(result);
if (html.includes('>Depart<') || html.includes('>Arrive<')) throw new Error('Builder visibility must hide departure and arrival');
console.log('travel result formatter checks passed');

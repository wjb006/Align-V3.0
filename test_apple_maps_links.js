const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('static/personal-planner.js', 'utf8');
const context = {
  state: { boot: null },
  escapeHtml: value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char])),
  document: { addEventListener: () => {}, querySelector: () => null },
  window: { isSecureContext: true, clearTimeout: () => {}, setTimeout: () => 0 },
  navigator: {},
  modalRoot: { querySelector: () => null, innerHTML: '' },
  URLSearchParams,
  setTimeout,
  clearTimeout,
};
vm.createContext(context);
vm.runInContext(source, context);

const url = context.appleDirectionsURL('Home', 'Arrowe Park Hospital, Wirral', 'bus');
if (!url.startsWith('https://maps.apple.com/directions?')) throw new Error('Must use unified Apple Maps directions URL');
const parsed = new URL(url);
if (parsed.searchParams.get('source') !== 'Home') throw new Error('Apple Maps source missing');
if (parsed.searchParams.get('destination') !== 'Arrowe Park Hospital, Wirral') throw new Error('Apple Maps destination missing');
if (parsed.searchParams.get('mode') !== 'transit') throw new Error('Bus journeys must request transit mode');
if (parsed.searchParams.get('transit-preferences') !== 'bus') throw new Error('Bus transit preference missing');

const link = context.appleDestinationLink('1 Test Road, Wirral', '', 'Test destination');
if (!link.includes('class="apple-maps-link"')) throw new Error('Destination link class missing');
if (!link.includes('Test destination')) throw new Error('Destination display label missing');
if (!link.includes('maps.apple.com/directions?')) throw new Error('Destination must link to an Apple Maps route');

if (source.includes("https://maps.apple.com/?")) throw new Error('Legacy Apple Maps query URL should not remain');

console.log('Apple Maps link checks passed');

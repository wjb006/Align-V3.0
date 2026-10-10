const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('static/journey-breakdown.js', 'utf8');
const context = {
  escapeHtml: value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char])),
};
vm.createContext(context);
vm.runInContext(source, context);

const bus = context.journeyBreakdown([{
  mode: 'bus',
  service: '407',
  from: 'Birkenhead Bus Station',
  to: 'Arrowe Park Hospital',
  start: '2030-01-01T08:00:00+00:00',
  end: '2030-01-01T08:25:00+00:00',
}]);
if (!bus.includes('journey-mode-bus')) throw new Error('Bus artwork class missing');
if (!bus.includes('journey-icon-badge') || !bus.includes('>407<')) throw new Error('Bus number must appear on the bus artwork');

const longBus = context.journeyBreakdown([{
  mode: 'bus', service: 'Liverpool to Chester', from: 'A', to: 'B',
  start: '2030-01-01T08:00:00+00:00', end: '2030-01-01T08:20:00+00:00',
}]);
if (longBus.includes('journey-icon-badge')) throw new Error('A long route name must not be squeezed onto the bus artwork');

const train = context.journeyBreakdown([{
  mode: 'rail',
  service: 'Merseyrail',
  platform: '2',
  from: 'Birkenhead Central',
  to: 'Liverpool Central',
  start: '2030-01-01T08:30:00+00:00',
  end: '2030-01-01T08:38:00+00:00',
}]);
if (!train.includes('journey-mode-train')) throw new Error('Train artwork class missing');
if (!train.includes('journey-icon-badge') || !train.includes('>P2<')) throw new Error('Platform badge must appear on the train artwork');
if (!train.includes('Platform 2')) throw new Error('Accessible platform text must remain visible');

console.log('journey artwork badge checks passed');

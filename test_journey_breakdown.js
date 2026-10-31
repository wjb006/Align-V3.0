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


const eventNotes = `[Align travel]
Leave home: 2030-01-01 07:42
Arrive at event location: 08:50 · Event: 09:00
Bus 407 · Birkenhead Bus Station 08:00 → Arrowe Park Hospital 08:25
Walk approximately 5 minutes
[/Align travel]
[Align travel steps]
${JSON.stringify([
  {mode:'walk',minutes:7},
  {mode:'bus',service:'407',minutes:25,start:'2030-01-01T08:00:00+00:00',end:'2030-01-01T08:25:00+00:00',from:'Birkenhead Bus Station',to:'Arrowe Park Hospital'},
  {mode:'walk',minutes:5}
])}
[/Align travel steps]`;
const eventSummary = context.journeyEventSummary(eventNotes);
if (!eventSummary.includes('Leave') || !eventSummary.includes('07:42')) throw new Error('Event card must show the leave time');
if (!eventSummary.includes('Bus 407') || !eventSummary.includes('08:00')) throw new Error('Event card must show the bus service and departure time');
if (!eventSummary.includes('Arrive') || !eventSummary.includes('08:50')) throw new Error('Event card must show the final arrival time');
if (!eventSummary.includes('Birkenhead Bus Station') || !eventSummary.includes('Walk') || !eventSummary.includes('Arrowe Park Hospital')) throw new Error('Expanded journey details must include walking and transit legs');


const betaNotes = `[Align travel]
Leave: 07:42
Bus 407 · 25 min · 08:00 · Birkenhead Bus Station → Arrowe Park Hospital
Walk approximately 5 minutes
Arrive: 08:50
[/Align travel]`;
const betaSummary = context.journeyEventSummary(betaNotes);
if (!betaSummary.includes('Bus 407') || !betaSummary.includes('08:00')) throw new Error('Beta-era saved service details must remain visible');
if (!betaSummary.includes('07:42') || !betaSummary.includes('08:50')) throw new Error('Beta-era leave and arrival times must remain visible');
if (!betaSummary.includes('Birkenhead Bus Station')) throw new Error('Beta-era route legs must remain readable');

console.log('journey artwork and event summary checks passed');

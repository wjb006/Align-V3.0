const fs = require('fs');

const home = fs.readFileSync('static/desktop.html', 'utf8');
const script = fs.readFileSync('static/desktop.js', 'utf8');
const calendar = fs.readFileSync('static/management-studio-calendar.js', 'utf8');
const nav = fs.readFileSync('static/management-studio-nav.js', 'utf8');
const installer = fs.readFileSync('installer/windows/Install-Align-Studio.ps1', 'utf8');

if (!home.includes('href="/"') || !home.includes('href="/management-studio"')) {
  throw new Error('Desktop home must open the planner and Management Studio');
}
if (!home.includes('This computer') || !home.includes('getalign.co.uk')) {
  throw new Error('Desktop home must label local Align and the hosted site');
}
if (!script.includes('/api/health') || !script.includes('/api/desktop/status')) {
  throw new Error('Desktop home must read the local health checks');
}
if (!calendar.includes('data-event-key') || !calendar.includes('/api/organiser-events/')) {
  throw new Error('Working calendar must open and save real Align events');
}
if (!calendar.includes('const startMin') || !calendar.includes('const endMin')) {
  throw new Error('Day/hour view must position events by start and end');
}
if (!calendar.includes('overlaps(e, dayStart(d), nextDay(d))')) {
  throw new Error('Calendar days must include events that overlap the day');
}
if (!calendar.includes('data-hour-now') || !calendar.includes('is-now') || !calendar.includes('wrap.scrollTop') || !calendar.includes('hourAnchored')) {
  throw new Error('Day/hour view must scroll to and mark the current hour');
}
if (!calendar.includes('previousScroll')) {
  throw new Error('Day/hour view must keep the scroll position when an event is opened');
}
if (!nav.includes("fetch('/api/health'")) throw new Error('Host overview must read /api/health');
if (!nav.includes('The public website was not checked')) throw new Error('Host overview must say the public site was not checked');
if (nav.includes('Live check not connected')) throw new Error('Host overview still shows the old disconnected placeholder');
if (installer.includes('Remove-Item $ExistingDatabase')) {
  throw new Error('The Windows installer still deletes the planner database');
}
const spec = fs.readFileSync('desktop/align.spec', 'utf8');
if (!spec.includes('align.ico')) throw new Error('The Windows executable build must embed align.ico');
if (!fs.existsSync('static/icons/align.ico')) throw new Error('align.ico is missing');
for (const size of [16, 24, 32, 48, 180, 192, 512]) {
  if (!fs.existsSync(`static/icons/align-${size}.png`)) throw new Error(`align-${size}.png is missing`);
}
const ico = fs.readFileSync('static/icons/align.ico');
if (ico.readUInt16LE(0) !== 0 || ico.readUInt16LE(2) !== 1) throw new Error('align.ico is not an icon file');
const icoCount = ico.readUInt16LE(4);
const icoSizes = [];
for (let i = 0; i < icoCount; i++) icoSizes.push(ico[6 + i * 16] || 256);
for (const size of [16, 24, 32, 256]) {
  if (!icoSizes.includes(size)) throw new Error(`align.ico is missing the ${size}px image`);
}
if (!installer.includes('align.ico') || !installer.includes('IconLocation')) {
  throw new Error('The Windows shortcut must use align.ico');
}
if (!home.includes('/icons/align-source.png')) throw new Error('Desktop home must show the Align icon');

console.log('Desktop shell checks passed');

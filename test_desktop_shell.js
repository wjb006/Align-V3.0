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
if (!nav.includes("fetch('/api/health'")) throw new Error('Host overview must read /api/health');
if (!nav.includes('The public website was not checked')) throw new Error('Host overview must say the public site was not checked');
if (nav.includes('Live check not connected')) throw new Error('Host overview still shows the old disconnected placeholder');
if (installer.includes('Remove-Item $ExistingDatabase')) {
  throw new Error('The Windows installer still deletes the planner database');
}

console.log('Desktop shell checks passed');

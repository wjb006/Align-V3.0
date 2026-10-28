const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const context = {};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/dates.js', 'utf8'), context);

assert.equal(context.formatDisplayDate('2026-10-07'), '07/10/2026');
assert.equal(context.formatDisplayDate('2026-10-07T14:30:00'), '07/10/2026');
assert.equal(context.formatDisplayDateTime('2026-10-07T14:30:00'), '07/10/2026 14:30');
assert.equal(context.formatDisplayDateTime('2026-10-07T08:00:00Z'), '07/10/2026 09:00');
assert.equal(context.formatDisplayDateTime(''), '');
assert.equal(context.formatDatesInText('checked 7 Oct 2026 14:30'), 'checked 07/10/2026 14:30');
assert.equal(context.formatDatesInText('Leave home: 7 Oct 06:40\nchecked 7 Oct 2026 09:00'), 'Leave home: 07/10/2026 06:40\nchecked 07/10/2026 09:00');

const app = fs.readFileSync('static/app.js', 'utf8');
if (!app.includes('return formatDisplayDate(value);')) throw new Error('prettyDate does not use the shared formatter');
const index = fs.readFileSync('static/index.html', 'utf8');
if (!index.includes('/dates.js?v=156-v56')) throw new Error('index.html does not load dates.js');
const widget = fs.readFileSync('static/align-widget.js', 'utf8');
const widgetDate = widget.match(/function widgetDate\(iso\) \{[\s\S]*?\n\}/);
if (!widgetDate) throw new Error('widget display date helper is missing');
vm.runInContext(widgetDate[0] + '; this.widgetDate = widgetDate;', context);
assert.equal(context.widgetDate('2026-10-07'), '07/10/2026');

console.log('PASS: shared display dates are DD/MM/YYYY');

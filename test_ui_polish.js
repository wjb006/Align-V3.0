const fs = require('fs');

const css = fs.readFileSync('static/styles.css', 'utf8');
const app = fs.readFileSync('static/app.js', 'utf8');
const index = fs.readFileSync('static/index.html', 'utf8');
const worker = fs.readFileSync('static/service-worker.js', 'utf8');
const travel = fs.readFileSync('static/travel-assets.js', 'utf8');

function token(name) {
  const match = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (!match) throw new Error(`Missing colour token --${name}`);
  return match[1];
}

function luminance(hex) {
  const channels = [0, 2, 4].map(index => parseInt(hex.slice(1 + index, 3 + index), 16) / 255);
  const linear = channels.map(channel => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrast(foreground, background) {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

if (contrast(token('muted'), token('canvas')) < 4.5) throw new Error('Muted text does not meet WCAG AA on the canvas');
if (contrast(token('nav-ink'), token('surface')) < 4.5) throw new Error('Navigation text does not meet WCAG AA');
if (!css.includes('--tap: 44px')) throw new Error('44px tap target token is missing');
if (!css.includes('min-height: var(--tap)')) throw new Error('Controls do not use the tap target token');
if (!css.includes('--shell: 960px')) throw new Error('Desktop shell width is missing');
if (!css.includes('#toast[data-tone="error"]')) throw new Error('Error toast tone is missing');
if (!css.includes('--edit-background: #061326 !important')) throw new Error('Dark theme does not override formatted page colours');
if (css.includes('white-space: nowrap; max-width: calc(100vw - 32px)')) throw new Error('Toast still truncates messages');
if (!index.includes('class="skip-link"') || !index.includes('header-install') || !/>\s*Install\s*</.test(index) || index.includes('⇧')) throw new Error('Install affordance or skip link is missing');
if (!app.includes('function installPanel()') || !app.includes('data-action="prompt-install"')) throw new Error('Install panel is missing');
if (!app.includes('form.checkValidity()') || !app.includes('function showFormError(') || !app.includes("addEventListener('invalid'")) throw new Error('Inline form validation is missing');
if (!travel.includes('f.checkValidity()') || !travel.includes('class="secondary-button" data-t150="search"')) throw new Error('Travel form feedback is missing');
if (!index.includes('156-v56') || !app.includes('`${BUILD_VERSION}-v56`') || !worker.includes('`${BUILD}-v56`')) throw new Error('Offline cache version was not bumped');
if (!worker.includes('align-v13-shell-${ASSET_VERSION}')) throw new Error('Service worker shell cache name changed');

console.log('UI polish checks passed');

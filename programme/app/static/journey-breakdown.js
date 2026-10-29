function journeyClock(value) {
 if (!value) return '';
 if (/^(?:[01]?\d|2[0-3]):[0-5]\d$/.test(String(value))) return String(value);
 const date = new Date(value);
 return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit'});
}
/* EASY TO EDIT: your uploaded icons and labels for each journey step. */
const JOURNEY_ICONS = {
  walk: {label:'Walk', image:'/journey-icons/walking.png'},
  bus: {label:'Bus', image:'/journey-icons/bus.png'},
  train: {label:'Train', image:'/journey-icons/train.png'},
  wait: {label:'Wait / connection', image:''},
  drive: {label:'Drive', image:''},
  transit: {label:'Public transport', image:''},
};
function journeyModeKey(mode) { return mode === 'rail' ? 'train' : String(mode || 'transit').toLowerCase(); }
function journeyPlatformBadge(value) {
 const platform=String(value||'').trim();
 if(!platform)return '';
 return /^p(?:latform)?\s*/i.test(platform)?platform.replace(/^platform\s*/i,'P'):'P'+platform;
}
function journeyModeArtwork(step,size=56) {
 const e=escapeHtml,key=journeyModeKey(step.mode),icon=JOURNEY_ICONS[key]||JOURNEY_ICONS.transit;
 if(!icon.image)return '';
 const serviceNumber=String(step.service_number||step.service||'').trim();
 const busNumber=/^[A-Z]?\d{1,4}[A-Z]?$/i.test(serviceNumber)?serviceNumber:'';
 const badge=key==='bus'?busNumber:key==='train'&&step.platform?journeyPlatformBadge(step.platform):'';
 const badgeTitle=key==='bus'&&badge?`Bus ${badge}`:key==='train'&&badge?`Platform ${String(step.platform).trim()}`:'';
 return `<span class="journey-mode-art journey-mode-${e(key)}" style="--journey-icon-size:${Number(size)||56}px"><img src="${e(icon.image)}" alt="" aria-hidden="true">${badge?`<span class="journey-icon-badge" title="${e(badgeTitle)}">${e(badge)}</span>`:''}</span>`;
}
function journeyBreakdown(steps = []) {
 const e=escapeHtml;
 return `<ol class="journey-breakdown">${steps.map(s=>{
  const key=journeyModeKey(s.mode),icon=JOURNEY_ICONS[key]||JOURNEY_ICONS.transit;
  const clock=journeyClock;
  const start=s.expected_start||s.start,end=s.expected_end||s.end;
  const duration=s.minutes??(start&&end?Math.max(0,Math.ceil((new Date(end)-new Date(start))/60000)):null);
  return `<li class="journey-step">${journeyModeArtwork(s)}<div class="journey-step-copy"><strong>${e(icon.label)}${s.service?' '+e(s.service):''}${duration!==null?' · '+e(duration)+' min':''}</strong>${s.from||s.to?`<div>${e(s.from||'')} → ${e(s.to||'')}</div>`:''}${start||end?`<div>${e(clock(start))}${end?' – '+e(clock(end)):''}</div>`:''}${s.platform?`<div class="journey-platform">Platform ${e(s.platform)}</div>`:''}</div></li>`;
 }).join('')}</ol>`;
}


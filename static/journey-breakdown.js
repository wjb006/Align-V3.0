function journeyClock(value) {
 if (!value) return '';
 if (/^(?:[01]?\d|2[0-3]):[0-5]\d$/.test(String(value))) return String(value);
 const date = new Date(value);
 return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit'});
}
/* Align V3 iconography: inline line icons, no legacy Beta image assets. */
const JOURNEY_ICONS = {
  walk: {label:'Walk', glyph:'<circle cx="13" cy="4" r="2"/><path d="m10 22 2-6 2-3 3 2 3 1"/><path d="m12 10-3 3-4 1"/><path d="m14 13-2 4-4 2"/>'},
  bus: {label:'Bus', glyph:'<rect x="3" y="4" width="18" height="15" rx="3"/><path d="M3 10h18M7 19v2m10-2v2M7 15h.01M17 15h.01M7 4V2m10 2V2"/>'},
  train: {label:'Train', glyph:'<rect x="5" y="3" width="14" height="16" rx="3"/><path d="M8 7h8M8 12h.01M16 12h.01M8 19l-2 3m10-3 2 3M5 16h14"/>'},
  wait: {label:'Wait / connection', glyph:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'},
  drive: {label:'Drive', glyph:'<path d="m5 11 1.5-5h11L19 11l2 2v5h-2v2h-3v-2H8v2H5v-2H3v-5z"/><path d="M5 13h14M7 16h.01M17 16h.01"/>'},
  transit: {label:'Public transport', glyph:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/>'},
};
function journeyModeKey(mode) { return mode === 'rail' ? 'train' : String(mode || 'transit').toLowerCase(); }
function journeyPlatformBadge(value) {
 const platform=String(value||'').trim();
 if(!platform)return '';
 return /^p(?:latform)?\s*/i.test(platform)?platform.replace(/^platform\s*/i,'P'):'P'+platform;
}
function journeyModeArtwork(step,size=56) {
 const e=escapeHtml,key=journeyModeKey(step.mode),icon=JOURNEY_ICONS[key]||JOURNEY_ICONS.transit;
 const serviceNumber=String(step.service_number||step.service||'').trim();
 const busNumber=key==='bus' && /^[A-Z]?\d{1,4}[A-Z]?$/i.test(serviceNumber)?serviceNumber:'';
 const badge=key==='bus'?busNumber:key==='train'&&step.platform?journeyPlatformBadge(step.platform):'';
 const badgeTitle=key==='bus'&&badge?'Bus '+badge:key==='train'&&badge?'Platform '+String(step.platform).trim():'';
 return '<span class="journey-mode-art journey-mode-'+e(key)+'" style="--journey-icon-size:'+(Number(size)||56)+'px"><svg viewBox="0 0 24 24" role="img" aria-label="'+e(icon.label)+'" focusable="false"><g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+icon.glyph+'</g></svg>'+(badge?'<span class="journey-icon-badge" title="'+e(badgeTitle)+'">'+e(badge)+'</span>':'')+'</span>';
}

function journeyEventSummary(notes = '') {
 const source=String(notes||'');
 const block=source.match(/\\[Align travel\\]([\\s\\S]*?)(?:\\[\\/Align travel\\]|$)/i);
 if(!block)return '';
 const lines=block[1].split(/\\r?\\n/).map(line=>line.trim()).filter(Boolean);
 const clockFromLine=(pattern)=>{
  const line=lines.find(value=>pattern.test(value));
  const match=String(line||'').match(/\\b([01]?\\d|2[0-3]):[0-5]\\d\\b/);
  return match?match[0]:'';
 };
 const leave=clockFromLine(/^Leave(?: home)?\\b/i);
 const arrival=clockFromLine(/^Arrive at event location\\b/i)||clockFromLine(/^Arrive\\b/i);
 let steps=[];
 try{
  const raw=source.match(/\\[Align travel steps\\]([\\s\\S]*?)\\[\\/Align travel steps\\]/i);
  const parsed=raw?JSON.parse(raw[1]):[];
  if(Array.isArray(parsed))steps=parsed;
 }catch(_){}
 // Keep Beta-era saved event notes readable when they pre-date the structured steps block.
 if(!steps.length){
  steps=lines.map(line=>{
   const walk=line.match(/^Walk(?: approximately)?\\s+(\\d+)\\s+minutes?\\b/i);
   if(walk)return {mode:'walk',minutes:Number(walk[1])};
   const transitLine=line.match(/^(Bus|Train|Tram|Rail)\\s+(.+?)\\s+·\\s+(.+?)\\s+(\\d{1,2}:\\d{2})\\s*→\\s*(.+?)\\s+(\\d{1,2}:\\d{2})$/i);
   if(!transitLine)return null;
   const mode=transitLine[1].toLowerCase()==='rail'?'train':transitLine[1].toLowerCase();
   const serviceHead=transitLine[2].split(/\\s+towards\\s+/i);
   return {mode,service:serviceHead[0].trim(),from:transitLine[3].trim(),start:transitLine[4],to:transitLine[5].trim(),end:transitLine[6]};
  }).filter(Boolean);
 }
 const transit=steps.filter(step=>['bus','train','rail','tram'].includes(journeyModeKey(step.mode)));
 const items=[];
 const add=(label,time,step=null)=>{
  if(!time)return;
  const art=step?journeyModeArtwork(step,34):journeyModeArtwork({mode:'walk'},30);
  const service=step?.service?(' '+String(step.service).trim()):'';
  items.push('<span class="journey-time-icon">'+art+'<span class="journey-time-copy"><small>'+escapeHtml(label+service)+'</small><strong>'+escapeHtml(time)+'</strong></span></span>');
 };
 add('Leave',leave);
 transit.forEach(step=>add(journeyModeKey(step.mode)==='bus'?'Bus':'Train',journeyClock(step.expected_start||step.start),step));
 add('Arrive',arrival);
 if(!items.length)return '';
 const legs=steps.length?journeyBreakdown(steps):'<p class="helper">Detailed walking and service steps are not available for this journey.</p>';
 return '<details class="compact-event-details journey-event-details"><summary>'+items.join('')+'</summary>'+legs+'</details>';
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


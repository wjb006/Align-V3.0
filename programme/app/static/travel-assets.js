/* Travel and owner Asset Studio screens. No coordinates are saved by this UI. */
const travel150 = {items:null, places:{origin:[],destination:[]}, points:{}, searches:{}, timers:{}, result:null, error:'', status:null, busy:false, liveTimer:null, liveSignature:'', autoBusy:false, autoSignature:''};
const assets150 = {data:null,busy:false};
function travelScope150(key) { return '/private-travel/'+encodeURIComponent(state.boot?.beta?.email || 'local')+'/'+key; }
function travelTime150(value) { return formatDisplayDateTime(value, 'Europe/London'); }
function travelJourneyCard150(j,r,index) {
 const legs=j.legs||[], modes=[...new Set(legs.map(l=>l.mode).filter(Boolean))].join(' · ')||'Journey';
 const provider=j.provider||legs.find(l=>l.provider)?.provider||'Scheduled service';
 const adjustments=[j.weather_adjustment,j.traffic_adjustment,j.weather_buffer,j.traffic_buffer].filter(Boolean);
 const leave=j.leave_at||j.leave_by;
 const settings=state.boot?.builder?.document?.travel_results||{}, visibility={leave_by:true,departure_arrival:true,duration:true,mode_provider:true,weather_adjustment:true,traffic_adjustment:true,actions:true,...(settings.visibility||{})};
 const shownAdjustments=[visibility.weather_adjustment?j.weather_adjustment:'',visibility.traffic_adjustment?j.traffic_adjustment:'',visibility.weather_adjustment?j.weather_buffer:'',visibility.traffic_adjustment?j.traffic_buffer:''].filter(Boolean);
 return `<article class="travel-result-card ${index===0?'travel-result-best':''}" data-journey-index="${index}">
   <div class="travel-result-heading"><div><p class="eyebrow">${index===0?'Best available choice':'Alternative'}</p><h3>${escapeHtml((j.badges||[]).join(' · ')||modes)}</h3></div>${visibility.mode_provider?`<span class="travel-provider">${escapeHtml(provider)}</span>`:''}</div>
   ${visibility.departure_arrival?`<div class="travel-times"><div><small>Depart</small><strong>${escapeHtml(travelTime150(j.departure))}</strong></div><span aria-hidden="true">→</span><div><small>Arrive</small><strong>${escapeHtml(travelTime150(j.arrival))}</strong></div></div>`:''}
   ${visibility.duration?`<div class="travel-meta"><span>${Math.round(j.duration||0)} min</span><span>${Math.round(j.walking||0)} min walking</span><span>${j.changes||0} changes</span></div>`:''}
   ${visibility.leave_by&&leave?`<p class="travel-leave"><strong>Leave by</strong> ${escapeHtml(travelTime150(leave))}</p>`:''}
   ${shownAdjustments.length?`<p class="travel-adjustments"><strong>Extra time</strong> ${escapeHtml(shownAdjustments.join(' · '))}</p>`:''}
   <p class="travel-live">${r.cached||!j.live?'Scheduled times — live updates unavailable':'Live information available'}</p>
   ${visibility.actions?journeyBreakdown(legs):''}
   ${(j.attributions||[]).map(a=>`<p class="helper">${escapeHtml(a)}</p>`).join('')}
 </article>`;
}
function renderTravel150() {
 travel150.points={};
 for(const side of ['origin','destination']){clearTimeout(travel150.timers[side]);travel150.searches[side]=(travel150.searches[side]||0)+1;}
 if (!travel150.items && !travel150.busy && !travel150.error) {
  travel150.busy=true;
  queueMicrotask(async()=>{
   try {
    travel150.status=await rawApi('/api/transport/status');
    if(!travel150.status.enabled)throw new Error('Travel routing is not enabled on this server.');
    if(!travel150.status.routing_configured)throw new Error('The journey provider needs configuring.');
    const data=await rawApi('/api/transport/items'); travel150.items=data.items;
   } catch(e){travel150.error=e.message;}
   finally {travel150.busy=false;if(state.tab==='transport')render();}
  });
 }
 return `<section class="page"><div class="add-head"><p class="eyebrow">Journeys</p><h1>Travel</h1><p class="subtle">Bus and rail journeys across Merseyside, with walking directions between stops.</p></div>${travel150.error?`<div class="card form-error" role="alert"><p>${escapeHtml(travel150.error)}</p><button type="button" class="secondary-button" data-t150="retry">Retry loading Travel</button></div>`:''}<form id="travel150" class="card settings-form">
 <label for="travel-event">Your shift or event</label><select id="travel-event" name="event_key" required><option value="">Choose an upcoming item</option>${(travel150.items||[]).map(i=>`<option value="${escapeHtml(i.key)}">${escapeHtml(i.title+' · '+travelTime150(i.start))}</option>`).join('')}</select>
 <p id="travel-destination-hint" class="helper">${travel150.busy?'Loading your items…':travel150.error?'Your items could not be loaded. Retry above.':!travel150.items?.length?'Add a timed shift or event with a destination first.':''}</p>
 ${['origin','destination'].map(k=>`<fieldset><legend>${k==='origin'?'Travel from':'Travel to'}</legend><label for="${k}-query">Address, stop, station or full postcode</label><input id="${k}-query" maxlength="240" autocomplete="off" value="${escapeHtml(k==='origin'?(state.boot?.settings?.user_address||''):'')}">${k==='origin'?'<button type="button" class="secondary-button" data-t150="location">Use my current location</button>':''}<div id="${k}-suggestions" class="travel-place-suggestions" role="listbox" aria-label="${k==='origin'?'Starting place':'Destination'} suggestions" hidden></div><select id="${k}-choice" data-place150="${k}" hidden><option value="">Choose a result</option></select><p id="${k}-selected" aria-live="polite"></p></fieldset>`).join('')}
 <label><input type="checkbox" id="postcode-consent"> Allow live address suggestions through HERE or OpenStreetMap and postcode lookup with Postcodes.io. Without this, suggestions use saved addresses and Align’s built-in stops.</label>
 <small class="helper">OpenStreetMap address results are attributed to © OpenStreetMap contributors.</small>
 <label>Arrive this many minutes early <input name="buffer" type="number" min="0" max="120" value="10" required></label>
 <fieldset><legend>Transport</legend><label><input name="bus" type="checkbox" checked> Bus</label><label><input name="rail" type="checkbox" checked> Rail</label><p>Walking to and between stops is included.</p></fieldset>
 <label><input name="consent" type="checkbox" required> Send these locations to ${escapeHtml(travel150.status?.provider||'the journey provider')} to find this journey.</label>
 <button class="primary-button" type="submit">Find journeys</button><button type="button" class="secondary-button" data-t150="saved">Show saved journey</button><p id="travel-message" role="status"></p></form><div id="travel-results150">${travelResult150(travel150.result)}</div></section>`;
}
function travelResult150(r) {
 if(!r)return '';
 const journeys=r.journeys||[], settings=state.boot?.builder?.document?.travel_results||{}, collapse=settings.show_best_only!==false, first=collapse?journeys.slice(0,1):journeys, alternatives=collapse?journeys.slice(1):[];
 return `<div class="card travel-results"><div class="travel-results-header"><div><h2>${r.cached?'Saved scheduled journeys':r.state==='on_time'?'Recommended journey':r.state==='late'?'Late alternatives':'Journey results'}</h2><p>${escapeHtml(r.message||'')}</p></div>${r.updated_at?`<small>Updated ${escapeHtml(travelTime150(r.updated_at))}${r.expired?' · timetable may be out of date':''}</small>`:''}</div>${first.map((j,i)=>travelJourneyCard150(j,r,i)).join('')}${alternatives.length&&settings.show_more!==false?`<button type="button" class="secondary-button travel-show-more" data-t150="toggle-more" aria-expanded="false" aria-controls="travel-alternatives150">Show more journeys (${alternatives.length})</button><div id="travel-alternatives150" class="travel-alternatives" hidden>${alternatives.map((j,i)=>travelJourneyCard150(j,r,i+1)).join('')}</div>`:''}</div>`;
}
function liveSignature150(r) {
 return (r?.journeys||[]).map(j => [j.disruption, ...(j.legs||[]).map(l => [l.service,l.expected_start,l.expected_end,l.cancelled].join('|'))].join(':')).join(';');
}
async function pollLiveTravel150() {
 const key=document.querySelector('#travel-event')?.value;
 if(!key||!travel150.result?.journeys?.length)return;
 try {
  const result=await api('/api/transport/live',{method:'POST',body:{event_key:key}});
  const signature=liveSignature150(result);
  if(travel150.liveSignature && signature!==travel150.liveSignature && typeof notifyAlign==='function') {
   const disrupted=(result.journeys||[]).some(j=>j.disruption&&j.disruption!=='none'||(j.legs||[]).some(l=>l.cancelled));
   if(disrupted) void notifyAlign('Align journey update','A saved journey has a new delay or disruption.','journey-live-'+key,'/transport');
  }
  travel150.liveSignature=signature;
  if(result.journeys?.length){travel150.result=result;const target=document.querySelector('#travel-results150');if(target)target.innerHTML=travelResult150(result);}
 } catch (_) {
  // Live status is optional; the saved scheduled journey remains usable.
 }
}
async function maybeAutoFindTravel150(){
 const f=document.querySelector('#travel150');if(!f||travel150.autoBusy)return;
 const key=f.elements.event_key?.value,origin=document.querySelector('#origin-query')?.value.trim(),destination=document.querySelector('#destination-query')?.value.trim();
 if(!key||!origin||!destination||!f.elements.consent?.checked)return;
 const signature=[key,origin,destination,JSON.stringify(travel150.points.origin||null),JSON.stringify(travel150.points.destination||null),f.elements.buffer.value,f.elements.bus.checked,f.elements.rail.checked].join('|');
 if(signature===travel150.autoSignature)return;travel150.autoSignature=signature;travel150.autoBusy=true;
 const message=document.querySelector('#travel-message');if(message)message.textContent='Both places selected. Finding journeys automatically…';
 try{
  const modes=['walk'];if(f.bus.checked)modes.push('bus');if(f.rail.checked)modes.push('rail');
  await api('/api/transport/preferences',{method:'POST',body:{arrival_buffer:Number(f.buffer.value),modes}});
  const r=await api('/api/transport/journeys',{method:'POST',body:{event_key:key,origin:travel150.points.origin,destination:travel150.points.destination,origin_address:origin,destination_address:destination,location_consent:f.elements.consent.checked}});
  travel150.result=r;travel150.liveSignature=liveSignature150(r);
  document.querySelector('#travel-results150').innerHTML=travelResult150(r);
  if(r.journeys?.length){clearInterval(travel150.liveTimer);travel150.liveTimer=setInterval(pollLiveTravel150,300000);void pollLiveTravel150();if(typeof AlignOffline!=='undefined'){const saved=await api('/api/transport/cached',{method:'POST',body:{event_key:key}});await AlignOffline.remember(travelScope150(key),saved);}}
  if(message)message.textContent=r.journeys?.length?'Journey times found and saved for this event.':'No matching journey found for these places.';
 }catch(error){if(message){message.textContent=error.message;message.classList.add('form-error');}travel150.autoSignature='';}
 finally{travel150.autoBusy=false;}
}
async function savedTravel150(key) {
 if(!key)throw new Error('Choose a shift or event first');
 let r;
 try { r=await api('/api/transport/cached',{method:'POST',body:{event_key:key}}); if(typeof AlignOffline!=='undefined')await AlignOffline.remember(travelScope150(key),r); }
 catch(e){ if(e.serverResponse)throw e; r=typeof AlignOffline!=='undefined'?await AlignOffline.cached(travelScope150(key)):null; if(!r)throw new Error('No journey saved on this phone. Find a journey while online first.'); }
 r=JSON.parse(JSON.stringify(r));r.cached=true;r.message='Saved scheduled journey — live updates unavailable. Check its date before travelling.';
 for(const j of r.journeys||[]){j.live=false;for(const l of j.legs||[])l.live=false;}
 travel150.result=r;document.querySelector('#travel-results150').innerHTML=travelResult150(r);
}
function renderAssets150() {
 if(!assets150.data&&!assets150.busy){assets150.busy=true;queueMicrotask(async()=>{try{assets150.data=await rawApi('/api/asset-studio');}catch(e){toast(e.message);}finally{assets150.busy=false;if(state.tab==='assets'&&assets150.data)render();}});}
 const d=assets150.data||{assets:[],categories:[]};
 return `<section class="page"><h1>Asset Studio</h1><p>Your image library. Upload an image, preview it and activate it for its category.</p><form id="assets-upload150" class="card settings-form"><label>Name<input name="name" maxlength="60" required></label><label>Image<input name="image" type="file" accept="image/png,image/jpeg,image/webp" required></label><img id="asset-preview150" alt="Selected image preview" hidden style="max-width:192px;max-height:192px"><label>Category<select name="category"><option value="">General image</option>${d.categories.map(c=>`<option value="${c.category_id}">${escapeHtml(c.category_group+' / '+c.display_name)}</option>`).join('')}</select></label><label>Image shape<select name="crop"><option value="fit">Keep proportions</option><option value="square">Square centre crop</option></select></label><button class="primary-button">Upload image</button><p id="asset-message150" role="status"></p></form>
 ${d.assets.map(a=>`<article class="card"><img src="/api/asset-studio/image/${a.asset_id}?v=${a.version}" alt="${escapeHtml(a.display_name)}" style="width:96px;height:96px;object-fit:contain"><h2>${escapeHtml(a.display_name)}</h2><p>${escapeHtml(a.status)}${d.categories.some(c=>c.default_asset_id===a.asset_id)?' · Category default':''}</p><div class="button-row">${['rename',a.status==='active'?'deactivate':'activate',...(a.status==='active'&&a.category_id?['default']:[])].map(action=>`<button data-a150="${action}" data-id="${a.asset_id}" data-version="${a.version}">${action==='default'?'Use for category':action[0].toUpperCase()+action.slice(1)}</button>`).join('')}</div></article>`).join('')||'<p>No images uploaded yet.</p>'}</section>`;
}
async function assetEncoded150(file){
 if(!file||file.size>10*1024*1024)throw new Error('Choose an image smaller than 10 MB');
 const bitmap=await createImageBitmap(file);const scale=Math.min(1,512/Math.max(bitmap.width,bitmap.height));const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
 const url=canvas.toDataURL('image/webp',0.88);if(url.length>850000)throw new Error('Choose a smaller image');return url.split(',')[1];
}
function clearTravelPlace150(side) {
 delete travel150.points[side];
 travel150.searches[side]=(travel150.searches[side]||0)+1;
 document.querySelector('#'+side+'-selected').textContent='';
 document.querySelector('#'+side+'-choice').innerHTML='<option value="">Choose a result</option>';const suggestions=document.querySelector('#'+side+'-suggestions');if(suggestions){suggestions.innerHTML='';suggestions.hidden=true;}
}
async function searchTravelPlace150(side, external=false) {
 const input=document.querySelector('#'+side+'-query'), query=input.value.trim();
 clearTravelPlace150(side);
 const version=travel150.searches[side];
 if(query.length<3)return;
 const r=await api('/api/transport/places',{method:'POST',body:{query,local_only:!external,consent:external&&document.querySelector('#postcode-consent').checked}});
 if(version!==travel150.searches[side]||input!==document.querySelector('#'+side+'-query')||query!==input.value.trim())return;
 const saved=[state.boot?.settings?.user_address,...(travel150.items||[]).map(i=>i.destination)].filter(v=>v&&v.toLowerCase().includes(query.toLowerCase()));
 travel150.places[side]=[...new Set(saved)].map(name=>({name})).concat(r.places);
 document.querySelector('#'+side+'-choice').innerHTML='<option value="">Choose a result</option>'+travel150.places[side].map((p,i)=>`<option value="${i}">${escapeHtml(p.name)}</option>`).join('');
 document.querySelector('#'+side+'-choice').size=Math.min(5,travel150.places[side].length+1);
 const suggestions=document.querySelector('#'+side+'-suggestions');if(suggestions){suggestions.innerHTML=travel150.places[side].map((p,i)=>`<button type="button" class="travel-place-option" role="option" data-place-suggestion="${side}" data-index="${i}"><strong>${escapeHtml(p.name)}</strong><small>Tap to use this place</small></button>`).join('');suggestions.hidden=!travel150.places[side].length;}
 document.querySelector('#'+side+'-selected').textContent=travel150.places[side].length?'Choose a suggestion, or keep your typed address.':'Keep your address; it will be located when you find journeys.';
}
document.addEventListener('input',e=>{
 if(!['origin-query','destination-query'].includes(e.target.id))return;
 const side=e.target.id.split('-')[0];clearTravelPlace150(side);clearTimeout(travel150.timers[side]);travel150.autoSignature='';
 travel150.timers[side]=setTimeout(()=>searchTravelPlace150(side,document.querySelector('#postcode-consent')?.checked===true).catch(err=>{const status=document.querySelector('#'+side+'-selected');if(status)status.textContent=err.message;}),850);
});
document.addEventListener('change',e=>{
 if(e.target.id==='postcode-consent'){for(const side of ['origin','destination']){const input=document.querySelector('#'+side+'-query');if(input?.value.trim().length>=3){clearTimeout(travel150.timers[side]);travel150.timers[side]=setTimeout(()=>searchTravelPlace150(side,e.target.checked).catch(()=>{}),200);}}}
 if(e.target.id==='travel-event'){const item=travel150.items?.find(i=>i.key===e.target.value);document.querySelector('#destination-query').value=item?.destination||'';clearTravelPlace150('destination');travel150.result=null;document.querySelector('#travel-results150').innerHTML='';clearInterval(travel150.liveTimer);const hint=document.querySelector('#travel-destination-hint');if(item?.destination)hint.innerHTML='Saved destination: '+appleDestinationLink(item.destination);else hint.textContent='Save an address on this item first.';travel150.autoSignature='';void maybeAutoFindTravel150().catch(()=>{});}
 if(e.target.dataset.place150){const side=e.target.dataset.place150;clearTimeout(travel150.timers[side]);travel150.searches[side]=(travel150.searches[side]||0)+1;const p=travel150.places[side][Number(e.target.value)];travel150.points[side]=e.target.value!==''?p?.point:null;if(p&&e.target.value!=='')document.querySelector('#'+side+'-query').value=p.name;document.querySelector('#'+side+'-selected').textContent=e.target.value!==''?p?.name||'':'';}
 if(e.target.matches('#assets-upload150 input[type=file]')){const f=e.target.files[0];const img=document.querySelector('#asset-preview150');if(img.dataset.url)URL.revokeObjectURL(img.dataset.url);if(f){img.dataset.url=URL.createObjectURL(f);img.src=img.dataset.url;img.hidden=false;}}
});
document.addEventListener('click',async e=>{
 const suggestion=e.target.closest('[data-place-suggestion]');if(suggestion){const side=suggestion.dataset.placeSuggestion,index=Number(suggestion.dataset.index),p=travel150.places[side]?.[index];if(!p)return;clearTimeout(travel150.timers[side]);travel150.points[side]=p.point||null;document.querySelector('#'+side+'-query').value=p.name;const select=document.querySelector('#'+side+'-choice');select.value=String(index);const list=document.querySelector('#'+side+'-suggestions');if(list)list.hidden=true;document.querySelector('#'+side+'-selected').textContent='Selected: '+p.name;travel150.autoSignature='';void maybeAutoFindTravel150();return;}
 const b=e.target.closest('[data-t150],[data-a150]');if(!b)return;e.preventDefault();b.disabled=true;
 try{
 if(b.dataset.a150){const action=b.dataset.a150;const body={action,id:Number(b.dataset.id),version:Number(b.dataset.version)};if(action==='rename'){body.name=prompt('Image name');if(body.name===null)return;}await rawApi('/api/asset-studio/change',{method:'POST',body});assets150.data=await rawApi('/api/asset-studio');render();return;}
 if(b.dataset.t150==='retry'){travel150.error='';travel150.items=null;render();return;}
 if(b.dataset.t150==='search')await searchTravelPlace150(b.dataset.side,true);
 if(b.dataset.t150==='location'){if(!navigator.geolocation)throw new Error('Location is unavailable');const p=await new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{timeout:15000,maximumAge:0}));clearTimeout(travel150.timers.origin);clearTravelPlace150('origin');document.querySelector('#origin-query').value='Current location';travel150.points.origin=[p.coords.latitude,p.coords.longitude];document.querySelector('#origin-selected').textContent='Current location selected for this journey';}
 if(b.dataset.t150==='saved')await savedTravel150(document.querySelector('#travel-event').value);
 if(b.dataset.t150==='toggle-more'){const panel=document.querySelector('#travel-alternatives150');const expanded=b.getAttribute('aria-expanded')==='true';b.setAttribute('aria-expanded',String(!expanded));b.textContent=expanded?`Show more journeys (${panel.children.length})`:'Show fewer journeys';panel.hidden=expanded;}
 }catch(err){toast(err.message);}finally{b.disabled=false;}
});
document.addEventListener('submit',async e=>{
 if(!['travel150','assets-upload150'].includes(e.target.id))return;e.preventDefault();e.stopImmediatePropagation();const f=e.target;const button=f.querySelector('button[type=submit],button.primary-button');
 if(typeof f.checkValidity==='function'&&!f.checkValidity()){f.querySelectorAll(':invalid').forEach(field=>field.setAttribute('aria-invalid','true'));f.reportValidity();return;}
 button.disabled=true;
 const message=f.querySelector('[role=status]');message.classList.remove('form-error');message.textContent='Working…';
 try{
 if(f.id==='assets-upload150'){const image=await assetEncoded150(f.image.files[0]);await rawApi('/api/asset-studio/upload',{method:'POST',body:{name:f.elements.name.value,category:f.category.value,crop:f.crop.value,image}});assets150.data=await rawApi('/api/asset-studio');render();toast('Image uploaded. Activate it when ready.');}
 else {if(!travel150.points.origin&&!document.querySelector('#origin-query').value.trim()||!travel150.points.destination&&!document.querySelector('#destination-query').value.trim())throw new Error('Enter both an origin and destination');const modes=['walk'];if(f.bus.checked)modes.push('bus');if(f.rail.checked)modes.push('rail');await api('/api/transport/preferences',{method:'POST',body:{arrival_buffer:Number(f.buffer.value),modes}});const key=f.event_key.value;const r=await api('/api/transport/journeys',{method:'POST',body:{event_key:key,origin:travel150.points.origin,destination:travel150.points.destination,origin_address:document.querySelector('#origin-query').value.trim(),destination_address:document.querySelector('#destination-query').value.trim(),location_consent:f.consent.checked}});travel150.result=r;travel150.liveSignature=liveSignature150(r);if(r.journeys?.length){clearInterval(travel150.liveTimer);travel150.liveTimer=setInterval(pollLiveTravel150,300000);pollLiveTravel150();}document.querySelector('#travel-results150').innerHTML=travelResult150(r);if(r.journeys?.length&&typeof AlignOffline!=='undefined'){const saved=await api('/api/transport/cached',{method:'POST',body:{event_key:key}});await AlignOffline.remember(travelScope150(key),saved);}message.textContent=r.journeys?.length?'Journey saved for offline viewing.':'No matching journey found.';}
 }catch(err){message.textContent=err.message;message.classList.add('form-error');}finally{button.disabled=false;}
},true);

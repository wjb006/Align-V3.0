const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const scope={FileManager:{local:()=>({joinPath:()=>'',libraryDirectory:()=>''})},DateFormatter:class {string(d){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(d)}}};
vm.createContext(scope);
vm.runInContext(fs.readFileSync('static/align-widget.js','utf8').split('if (!config.runsInWidget)')[0]+';this.select=viewEvents;',scope);
const events=['27','28','29','30'].map(day=>({day:'2026-09-'+day,start:'09:00',end:'17:00',title:'Event '+day,location:'Home'}));
events.push({day:'2026-10-04',start:'09:00',end:'17:00',title:'Event 4'},{day:'2026-10-05',start:'09:00',end:'17:00',title:'Event 5'});
const now=new Date('2026-09-28T19:00:00Z'),data={events};
assert.equal(scope.select(data,now,'today').length,1); // Today includes completed shifts.
assert.equal(scope.select(data,now,'next')[0].day,'2026-09-29');
assert.equal(scope.select(data,now,'3days').length,3);
assert.equal(scope.select(data,now,'week').length,4); // Seven dates, not eight.
const night={events:[{day:'2026-09-27',start:'22:00',end:'06:00',title:'Overnight'}]};
assert.equal(scope.select(night,new Date('2026-09-28T01:00:00Z'),'today').length,1);
assert.equal(scope.select(null,now,'week').length,0);
console.log('PASS: today, next, three-day and seven-day windows, overnight events, empty snapshot');

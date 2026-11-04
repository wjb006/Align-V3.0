const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('static/app.js','utf8');
const start=source.indexOf('function renderSectionsIndex() {');
const end=source.indexOf('\nfunction installPanel()',start);
assert(start>=0&&end>start,'Sections renderer must exist');
const context={state:{sectionDefinitions:[]},escapeHtml:value=>String(value??''),callOptional:()=>''};
vm.createContext(context);
vm.runInContext(source.slice(start,end),context);

let html=context.renderSectionsIndex();
assert(html.includes('data-action="work-opt-in"'),'Unconfigured Work must offer database opt-in');
assert(html.includes('Set up Work Calendar'),'Unconfigured Work must have a clear setup entry');
assert(!html.includes('data-action="work-setup"'),'Unconfigured Work must not skip the database opt-in step');

context.state.sectionDefinitions=[{key:'work',optional:true,enabled:false,name:'Work'}];
html=context.renderSectionsIndex();
assert(html.includes('data-action="work-opt-in"'),'Disabled Work must still offer opt-in');

context.state.sectionDefinitions=[{key:'work',optional:true,enabled:true,name:'Work',icon:'▣',colour:'#123456'}];
html=context.renderSectionsIndex();
assert(html.includes('data-action="work-setup"'),'Enabled Work must offer management settings');
assert(html.includes('data-action="work-rota"'),'Enabled Work must offer rota upload');
assert(!html.includes('data-action="work-opt-in"'),'Enabled Work must not ask the user to opt in again');
console.log('Work Calendar setup and management entry points passed');

const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('static/personal-planner.js', 'utf8').split('const travelLabels=')[0];
function harness(town, getCurrentPosition) {
 const timers=new Map(), requests=[]; let id=0;
 const context={renders:0,state:{tab:'today',boot:{beta:{email:'test@example.com'},personal:{preferences:{weather_town:town}}}},navigator:{geolocation:{getCurrentPosition}},personalPrefs(){return context.state.boot.personal.preferences;},render(){context.renders++;},
  api:async(path,options)=>{requests.push({path,options});return {place:town,current:{weather_code:0,temperature_2m:14}};},
  setTimeout:(fn,ms)=>{timers.set(++id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id)};
 context.window={isSecureContext:true,setTimeout:context.setTimeout,clearTimeout:context.clearTimeout};
 vm.createContext(context);vm.runInContext(source,context);
 return {context,timers,requests,run:code=>vm.runInContext(code,context)};
}
(async()=>{
 let late;
 const h=harness('Birkenhead',success=>{late=success;});
 const pending=h.run('loadPersonalWeather(true)');
 assert.equal(h.requests.length,0);
 [...h.timers.values()].find(t=>t.ms===10000).fn();
 await pending;
 assert.equal(h.requests.length,1);
 assert.equal(JSON.stringify(h.requests[0].options.body),'{}');
 assert.equal(h.run('weatherLoading'),false);
 assert.equal(h.run('personalWeather.place'),'Birkenhead');
 assert.equal(h.context.renders,1,'Today must repaint after weather completes');
 late({coords:{latitude:1,longitude:2}});
 assert.equal(h.requests.length,1);
 const denied=harness('',()=>{});
 const failed=denied.run('loadPersonalWeather(true)');
 [...denied.timers.values()].find(t=>t.ms===10000).fn();await failed;
 assert.equal(denied.run('weatherLoading'),false);
 assert.match(denied.run('weatherError'),/fallback weather town/);
 assert.equal(denied.context.renders,1,'Today must display errors rather than stale loading');
 const located=harness('Birkenhead',success=>success({coords:{latitude:53,longitude:-3}}));
 await located.run('loadPersonalWeather(true)');
 assert.equal(located.requests[0].options.body.latitude,53);
 assert.equal([...located.timers.values()].filter(t=>t.ms===10000).length,0);
 const home=harness('Birkenhead',success=>success({coords:{latitude:53.39,longitude:-3.01}}));
 home.context.state.tab='home';
 assert.match(home.run('homeWeatherChip()'),/Weather…/,'Home must show a loading chip and start the weather request');
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(home.requests.length,1,'Home dashboard must request weather without opening Today');
 assert.equal(home.requests[0].path,'/api/personal/weather');
 assert.equal(home.context.renders,1,'Home must repaint when the weather request completes');
 assert.match(home.run('homeWeatherChip()'),/°/,'Home must show the returned temperature');
 const homeError=harness('Birkenhead',success=>success({coords:{latitude:53.39,longitude:-3.01}}));
 homeError.context.state.tab='home';
 homeError.context.api=async()=>{throw new Error('Weather service unavailable');};
 homeError.run('homeWeatherChip()');
 await new Promise(resolve=>setImmediate(resolve));
 const failedChip=homeError.run('homeWeatherChip()');
 assert.match(failedChip,/Weather unavailable/,'Home must explain when weather cannot be loaded');
 assert.match(failedChip,/data-personal="weather"/,'Home must provide a working retry action');
 console.log('PASS: Home weather loads, shows failures with retry, and retains location timeout/fallback handling');
})().catch(e=>{console.error(e);process.exitCode=1;});

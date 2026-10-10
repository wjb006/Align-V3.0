const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('static/align-widget.js','utf8');
new (Object.getPrototypeOf(async function(){}).constructor)(source);
assert.ok(!source.includes('new WebView'));
async function run(mode) {
  let saved=null,calls=[];
  const scope={
    FileManager:{local:()=>({joinPath:()=>'',libraryDirectory:()=>'',fileExists:()=>false,writeString:(_,s)=>saved=JSON.parse(s)})},
    Alert:class {addTextField(){} addSecureTextField(){} addAction(){} addCancelAction(){} async presentAlert(){return mode==='cancel'?-1:0} textFieldValue(i){return i?'test-password':'test@example.invalid'}},
    Timer:{schedule:(_,repeat,callback)=>{const timer=setTimeout(callback,30);return {invalidate:()=>clearTimeout(timer)}}},
    Request:class {
      constructor(url){this.url=url}
      async loadString(){
        calls.push(this.url);assert.equal(this.onRedirect(),null);assert.equal(this.timeoutInterval,20);
        if(mode==='timeout')return new Promise(()=>{});
        this.response={statusCode:mode==='bad-login'?401:200,cookies:[{name:'align_beta',value:'test-session'}]};
        if(this.url.endsWith('/login')){assert.equal(JSON.parse(this.body).password,'test-password');return '{}'}
        assert.equal(this.headers.Cookie,'align_beta=test-session');
        if(this.url.endsWith('/bootstrap'))return JSON.stringify({beta:{},dashboard:{today:'2026-09-28'}});
        if(this.url.includes('/shifts?'))return JSON.stringify([{work_date:'2026-09-28',start_time:'09:00',end_time:'17:00',notes:'[Align travel]\nLeave at 08:15\n[/Align travel]'}]);
        return '{}';
      }
    }
  };
  vm.createContext(scope);vm.runInContext(source.split('function ukClock')[0]+';this.run=updateSchedule;',scope);
  if(mode==='bad-login'||mode==='timeout'){await assert.rejects(scope.run());assert.equal(saved,null)}
  else if(mode==='cancel'){assert.equal(await scope.run(),false);assert.equal(calls.length,0)}
  else {assert.equal(await scope.run(),true);assert.equal(saved.shifts[0].leave,'08:15');assert.ok(calls.at(-1).endsWith('/logout'));assert.ok(!JSON.stringify(saved).includes('test-password'))}
}
(async()=>{for(const mode of ['success','bad-login','timeout','cancel'])await run(mode);console.log('PASS: native sign-in, save, logout, rejected credentials, stalled request timeout and cancel');})().catch(e=>{console.error(e);process.exitCode=1});

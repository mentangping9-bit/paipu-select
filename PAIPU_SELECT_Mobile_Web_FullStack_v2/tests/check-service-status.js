const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let now=0,calls=0,reply={paused:true,retry_after:18000},ok=true;
const elements=Object.fromEntries(['servicePause','servicePauseTimer','servicePauseChecking'].map(k=>[k,{hidden:true,textContent:''}]));
const notice={hidden:false},events={},intervals=new Map();let id=0;
const document={hidden:false,getElementById:k=>elements[k],querySelector:()=>notice,addEventListener:(k,v)=>events[k]=v};
const context={document,performance:{now:()=>now},AbortSignal:{timeout:()=>null},setInterval:(f,ms)=>{intervals.set(++id,{f,ms});return id;},clearInterval:i=>intervals.delete(i),PaipuBackend:{request:async()=>{calls++;return {ok,json:async()=>reply};}}};
vm.createContext(context);vm.runInContext(fs.readFileSync('public/service-status.js','utf8'),context);
const flush=()=>new Promise(r=>setImmediate(r));
(async()=>{
 events['paipu-server-state']({detail:'ready'});await flush();
 assert.equal(calls,1);assert.equal(elements.servicePause.hidden,false);assert.equal(notice.hidden,true);
 assert.equal(elements.servicePauseTimer.textContent,'05:00:00');
 const tick=()=>{for(const {f,ms} of [...intervals.values()])if(ms===1000)f();};
 now=3661000;tick();assert.equal(elements.servicePauseTimer.textContent,'03:58:59');assert.equal(calls,1,'countdown must not poll each second');
 document.hidden=true;events.visibilitychange();assert.ok(![...intervals.values()].some(i=>i.ms===60000));
 // A failed refresh at zero retains the pause and checking notice.
 ok=false;document.hidden=false;now=18000000;tick();await flush();assert.equal(elements.servicePause.hidden,false);assert.equal(elements.servicePauseChecking.hidden,false);
 // Visible tab resumes request-driven checking; valid status closes the card.
 ok=true;reply={paused:false,retry_after:0};now+=60000;document.hidden=false;events.visibilitychange();await flush();
 assert.equal(elements.servicePause.hidden,true);assert.equal(notice.hidden,false);
 context.PaipuServiceStatus.pause({retry_after:400});assert.equal(elements.servicePauseTimer.textContent,'00:06:40');
 context.PaipuServiceStatus.pause({retry_after:999999});assert.equal(elements.servicePauseTimer.textContent,'00:06:40','reject invalid unbounded duration');
 assert.ok(!fs.readFileSync('public/service-status.js','utf8').includes('/api/convert'),'status must never trigger replay retrieval');
 console.log('PASS: countdown, failed reopen check, hidden tab, API pause, bounded reads and no upstream work');
})().catch(e=>{console.error(e);process.exitCode=1;});

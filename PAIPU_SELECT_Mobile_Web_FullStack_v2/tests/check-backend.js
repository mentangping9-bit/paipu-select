const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('public/backend.js','utf8');
(async()=>{
 let now=1000,calls=[],attempt=0;
 const token='A'.repeat(24)+'.'+'a'.repeat(32),events=[];
 const scope={Headers,AbortSignal,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},
  Date:{now:()=>now},setTimeout:(fn,ms)=>{now+=ms;queueMicrotask(fn);},
  document:{dispatchEvent:e=>events.push(e.detail)},PaipuBackendOrigin:'https://paipu-select.onrender.com',
  fetch:async(url,options)=>{
   calls.push({url,options});
   if(url.endsWith('/api/health'))return {ok:true,json:async()=>{if(++attempt<3)throw Error('Render loading page');return {status:'ok',version:'3.4.0'};},headers:new Headers()};
   return {ok:true,headers:new Headers({'X-Paipu-Visitor':token})};
  }};
 vm.createContext(scope);vm.runInContext(source,scope);
 const api=scope.PaipuBackend;
 const p=api.ready();assert.equal(p,api.ready());
 assert.equal((await p).version,'3.4.0');
 assert.equal(calls.length,3);assert.deepEqual(events,['starting','ready']);
 assert(calls.every(c=>c.url.endsWith('/api/health')));
 await api.request('/api/convert',{method:'POST'});
 await api.request('/api/convert/status?job=test');
 assert.equal(calls.at(-1).options.headers.get('X-Paipu-Visitor'),token);
 assert.equal(calls.at(-1).options.credentials,'omit');
 const n=calls.length;await api.ready();assert.equal(calls.length,n);
 now+=61000;await api.ready();assert.equal(calls.length,n+1);
 console.log('PASS: bounded cold-start recovery, one pending warmup, cookie-free queue identity, idle recheck');
})().catch(e=>{console.error(e);process.exitCode=1;});

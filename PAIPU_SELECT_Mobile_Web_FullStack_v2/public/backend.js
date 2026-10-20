/* Anonymous queue transport; never stores Mahjong Soul credentials. */
(() => {
'use strict';
const origin=globalThis.PaipuBackendOrigin||'';
let visitor='', pending=null, readyAt=0;
async function request(path, options={}){
 if(!path.startsWith('/api/'))throw Error('Invalid API path');
 const headers=new Headers(options.headers||{});
 if(origin&&visitor)headers.set('X-Paipu-Visitor',visitor);
 const response=await fetch(origin+path,{...options,headers,credentials:origin?'omit':'same-origin'});
 const next=response.headers.get('X-Paipu-Visitor');
 if(origin&&next&&/^[A-Za-z0-9_-]{24}\.[0-9a-f]{32}$/.test(next))visitor=next;
 return response;
}
function ready(){
 if(pending&&(!readyAt||Date.now()-readyAt<60000))return pending;
 pending=(async()=>{
  document.dispatchEvent(new CustomEvent('paipu-server-state',{detail:'starting'}));
  const deadline=Date.now()+120000;
  while(Date.now()<deadline){
   try{
    const response=await request('/api/health',{cache:'no-store',signal:AbortSignal.timeout(15000)});
    const data=await response.json();
    if(response.ok&&data.status==='ok'&&data.version){
     readyAt=Date.now();
     document.dispatchEvent(new CustomEvent('paipu-server-state',{detail:'ready'}));
     return data;
    }
   }catch{}
   await new Promise(resolve=>setTimeout(resolve,3000));
  }
  document.dispatchEvent(new CustomEvent('paipu-server-state',{detail:'failed'}));
  pending=null;
  throw Error('서버 준비에 시간이 걸립니다. 잠시 후 다시 시도해 주세요.');
 })();return pending;
}
globalThis.PaipuBackend=Object.freeze({request,ready,origin});
})();

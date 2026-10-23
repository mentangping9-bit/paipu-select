/* Public pause notice. Countdown is local; status reads never query the game. */
(() => {
'use strict';
const card=document.getElementById('servicePause');
const timer=document.getElementById('servicePauseTimer');
const checking=document.getElementById('servicePauseChecking');
const notice=document.querySelector('.service-notice');
let until=0, paused=false, pending=null, timerId=0, pollId=0;
let lastRead=-Infinity, ready=false;
const clock=()=>performance.now();
function render(){
 card.hidden=!paused;
 if(notice)notice.hidden=paused;
 const seconds=Math.max(0,Math.ceil((until-clock())/1000));
 timer.textContent=[Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(n=>String(n).padStart(2,'0')).join(':');
 checking.hidden=!paused||seconds>0;
}
function apply(data){
 if(typeof data.paused!=='boolean'||!Number.isFinite(data.retry_after)||data.retry_after<0||data.retry_after>18000)return;
 paused=data.paused;until=clock()+data.retry_after*1000;
 clearInterval(timerId);timerId=0;
 if(paused)timerId=setInterval(()=>{
  render();
  if(until<=clock()){clearInterval(timerId);timerId=0;refresh(true);}
 },1000);
 render();
}
async function refresh(force=false){
 if(!ready||document.hidden)return;
 if(pending)return pending;
 if(!force&&clock()-lastRead<60000)return;
 lastRead=clock();
 pending=(async()=>{
  try{
   const response=await globalThis.PaipuBackend.request('/api/service/status',{cache:'no-store',signal:AbortSignal.timeout(10000)});
   if(response.ok)apply(await response.json());
  }catch{} // An unavailable status must never announce a false reopening.
 })();
 try{await pending;}finally{pending=null;}
}
function schedule(){
 clearInterval(pollId);pollId=0;
 if(ready&&!document.hidden){refresh();pollId=setInterval(()=>refresh(),60000);}
}
document.addEventListener('paipu-server-state',event=>{if(event.detail==='ready'){ready=true;schedule();}});
document.addEventListener('visibilitychange',()=>{render();schedule();});
globalThis.PaipuServiceStatus=Object.freeze({pause(data){
 const seconds=Number(data.retry_after);
 if(Number.isFinite(seconds)&&seconds>0)apply({paused:true,retry_after:seconds});
}});
})();

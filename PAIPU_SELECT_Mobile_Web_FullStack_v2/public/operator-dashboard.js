/* Private dashboard presentation. Data arrives only through the existing
   operator-authorized endpoint; this module never fetches or stores credentials. */
(() => {
'use strict';
const $=id=>document.getElementById(id), I=globalThis.PaipuI18n, t=(s,v)=>I.t(s,v);
const locale=()=>({ko:'ko-KR',en:'en-GB',ja:'ja-JP'}[I.language]);
const number=n=>new Intl.NumberFormat(locale()).format(n??0);
const date=n=>n?new Intl.DateTimeFormat(locale(),{timeZone:'Asia/Seoul',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(n*1000)):t('없음');
const shortDay=s=>s?s.slice(5).replace('-','/'):t('없음');
let snapshot=null, expanded=null;
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function badge(text,kind=''){return el('span',text,'operator-badge '+kind);}
function state(a){
 if(!a.authenticated)return [t('인증 필요'),'warn',true];
 if(a.unavailable_reason)return [t('로그인 확인'),'warn',true];
 if(a.rate_limit_seconds>0)return [t('540 휴식'),'warn',true];
 if(a.cooldown_seconds>0)return [t('휴식 중'),'wait',true];
 if(snapshot.active_slot===a.slot)return [t('처리 중'),'active',false];
 const budget=snapshot.scheduler?.accounts?.[String(a.slot)];
 if(budget?.retry_after>0)return [t('보호 대기'),'wait',false];
 return [t('정상'),'ok',false];
}
function selectedAccount(){
 const account=snapshot?.accounts.find(a=>String(a.slot)===$('accountSlot').value);
 $('selectedAccountEmail').textContent=account?account.email+' · '+account.region.toUpperCase():'';
}
function pair(parent,label,value){const item=el('div');item.append(el('dt',t(label)),el('dd',value));parent.append(item);}
function detail(a){
 const box=el('div',undefined,'operator-account-detail'), list=el('dl');
 const b=snapshot.scheduler?.accounts?.[String(a.slot)];
 pair(list,'이메일',a.email);pair(list,'인증 지역',a.region.toUpperCase());
 pair(list,'오늘 성공 / 실패',number(a.usage?.today?.successes)+' / '+number(a.usage?.today?.failures));
 pair(list,'누적 성공 / 실패',number(a.usage?.total?.successes)+' / '+number(a.usage?.total?.failures));
 pair(list,'마지막 조회',date(a.usage?.last_attempt_at));
 pair(list,'최근 실패',a.usage?.last_failure_at?date(a.usage.last_failure_at)+' · '+t('코드 {n}',{n:a.usage.last_error_code??'—'}):t('없음'));
 pair(list,'진행 중·결과 미확인',number(a.usage?.unfinished));
 if(b){pair(list,'최근 10분 / 6시간',number(b.short_attempts)+' / '+number(b.long_attempts));pair(list,'보호 대기',t('{n}초',{n:Math.max(a.cooldown_seconds||0,b.retry_after||0)}));pair(list,'조회 여유 회복 간격',t('{n}초',{n:b.refill_seconds}));}
 if(a.unavailable_reason)pair(list,'로그인 확인',a.unavailable_reason);
 box.append(list);return box;
}
function renderAccounts(){
 const table=el('table',undefined,'operator-accounts'), head=table.createTHead().insertRow();
 for(const [i,label] of ['계정','상태','오늘','누적','최근 조회'].entries()){const th=el('th',t(label),i===4?'operator-last':'');th.scope='col';head.append(th);}
 const body=table.createTBody();
 const rows=snapshot.accounts.filter(a=>$('accountFilter').value!=='attention'||state(a)[2]);
 for(const a of rows){
  const row=body.insertRow(), [label,kind]=state(a), cell=el('th');cell.scope='row';
  const button=el('button',String(a.slot),'operator-account-button');button.type='button';
  button.setAttribute('aria-label',t('계정 {n} 상세',{n:a.slot}));button.setAttribute('aria-expanded',String(expanded===a.slot));
  button.setAttribute('aria-controls','account-detail-'+a.slot);
  button.onclick=()=>{expanded=expanded===a.slot?null:a.slot;renderAccounts();$('account-toggle-'+a.slot)?.focus();};button.id='account-toggle-'+a.slot;
  cell.append(button);row.append(cell);row.insertCell().append(badge(label,kind));
  row.insertCell().textContent=number(a.usage?.today?.attempts);row.insertCell().textContent=number(a.usage?.total?.attempts);
  const last=row.insertCell();last.className='operator-last';last.textContent=date(a.usage?.last_attempt_at);
  const more=body.insertRow();more.id='account-detail-'+a.slot;more.hidden=expanded!==a.slot;more.className='operator-detail-row';
  if(expanded===a.slot){const d=more.insertCell();d.colSpan=5;d.append(detail(a));}
 }
 $('usageCards').replaceChildren(table);$('accountFilterEmpty').hidden=rows.length!==0;
}
function renderTrend(){
 const all=snapshot.daily_usage?.days||[], days=all.slice(-Number($('usagePeriod').value||7));
 const known=days.filter(d=>d.known), max=Math.max(1,...known.flatMap(d=>[d.attempts,d.successes,d.failures]));
 const top=Math.max(1,Math.ceil(max/4)*4), w=720,h=222,left=44,right=704,base=174,plot=148;
 const ns='http://www.w3.org/2000/svg', svg=document.createElementNS(ns,'svg');
 svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',t('일별 패보 조회 추이'));
 function shape(tag,attrs,text){const node=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))node.setAttribute(k,String(v));if(text!==undefined)node.textContent=text;svg.append(node);return node;}
 const x=i=>left+(right-left)*(days.length<=1?.5:i/(days.length-1)), y=v=>base-plot*v/top;
 for(const v of [0,top/2,top]){shape('line',{x1:left,y1:y(v),x2:right,y2:y(v),class:'chart-grid'});shape('text',{x:left-9,y:y(v)+4,'text-anchor':'end',class:'chart-label'},number(v));}
 for(let i=0;i<days.length;i++){if(i===0||i===days.length-1||i%Math.ceil(days.length/6)===0)shape('text',{x:x(i),y:201,'text-anchor':'middle',class:'chart-label'},shortDay(days[i].day));}
 for(const [metric,cls] of [['attempts','chart-attempt'],['successes','chart-success'],['failures','chart-failure']]){
  const points=days.flatMap((d,i)=>d.known?[[x(i),y(d[metric])]]:[]);
  if(points.length>1)shape('polyline',{points:points.map(p=>p.join(',')).join(' '),class:'chart-series '+cls});
  days.forEach((d,i)=>{if(!d.known)return;
   const dot=shape('circle',{cx:x(i),cy:y(d[metric]),r:3.5,class:'chart-dot '+cls});
   const title=document.createElementNS(ns,'title');title.textContent=d.day+' · '+t('조회 시도')+' '+number(d.attempts)+' · '+t('성공')+' '+number(d.successes)+' · '+t('실패')+' '+number(d.failures);dot.append(title);
  });
 }
 if(!known.length)shape('text',{x:374,y:100,'text-anchor':'middle',class:'chart-label'},t('선택한 기간의 기록이 없습니다.'));
 $('usageChart').replaceChildren(svg);
 $('usageTrendNote').textContent=t('일별 기록: {day}부터 · 이전 기록 없음',{day:snapshot.daily_usage?.started_day||'—'});
 const table=el('table',undefined,'operator-daily'), header=table.createTHead().insertRow();
 for(const label of ['날짜','조회 시도','성공','실패']){const th=el('th',t(label));th.scope='col';header.append(th);}
 const body=table.createTBody();
 for(const d of [...days].reverse()){const row=body.insertRow(),th=el('th',shortDay(d.day));th.scope='row';row.append(th);for(const metric of ['attempts','successes','failures'])row.insertCell().textContent=d.known?number(d[metric]):'—';}
 $('usageDailyTable').replaceChildren(table);
}
function render(data){
 snapshot=data;
 const total=data.accounts.reduce((s,a)=>({today:s.today+(a.usage?.today?.attempts||0),total:s.total+(a.usage?.total?.attempts||0),success:s.success+(a.usage?.today?.successes||0),failure:s.failure+(a.usage?.today?.failures||0),last:Math.max(s.last,a.usage?.last_attempt_at||0)}),{today:0,total:0,success:0,failure:0,last:0});
 $('usageTodayTotal').textContent=number(total.today);$('usageAllTotal').textContent=number(total.total);
 $('usageTodayOutcomes').textContent=t('성공 {s} · 실패 {f}',{s:number(total.success),f:number(total.failure)});
 const ready=data.accounts.filter(a=>a.authenticated&&!a.unavailable_reason&&!(a.cooldown_seconds>0)&&!(data.scheduler?.accounts?.[String(a.slot)]?.retry_after>0)).length;
 $('usageReadyTotal').textContent=ready+' / '+data.accounts.length;
 $('usageRestTotal').textContent=t('540 휴식 {n}개',{n:data.accounts.filter(a=>a.rate_limit_seconds>0).length});
 $('usageLastAttempt').textContent=date(total.last);
 const flow=$('operatorFlow');flow.replaceChildren();
 if(data.protection?.paused)flow.append(badge(t('신규 조회 중단 · {n}분',{n:Math.ceil(data.protection.retry_after/60)}),'warn'));
 flow.append(badge(t('처리 {slot}',{slot:data.active_slot?'#'+data.active_slot:'—'})),badge(t('다음 {slot}',{slot:data.next_slot?'#'+data.next_slot:'—'})));
 if(data.scheduler?.enabled)flow.append(badge(t('조회 간격 {n}초',{n:data.scheduler.interval_seconds})));
 $('usageInfo').textContent=(data.usage_started_at?t('집계 시작: {time} · 한국시간 기준',{time:date(data.usage_started_at)}):t('첫 조회부터 집계됩니다.'))+' '+t('캐시 재사용·대기열 확인·이메일 인증은 제외됩니다. 성공·실패는 처리 완료일 기준입니다.')+(data.usage_persistent?'':' '+t('메모리 통계: 서버 재시작 시 초기화됩니다.'));
 $('accountUsage').hidden=false;renderTrend();renderAccounts();selectedAccount();
}
$('usagePeriod').onchange=()=>{if(snapshot)renderTrend();};
$('accountFilter').onchange=()=>{if(snapshot)renderAccounts();};
function clear(){snapshot=null;expanded=null;$('accountUsage').hidden=true;$('usageCards').replaceChildren();$('usageChart').replaceChildren();$('usageDailyTable').replaceChildren();$('selectedAccountEmail').textContent='';}
globalThis.PaipuOperatorDashboard={render,selectedAccount,clear};
})();

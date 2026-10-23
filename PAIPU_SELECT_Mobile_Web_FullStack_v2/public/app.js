(() => {
'use strict';
const $ = id => document.getElementById(id);
const parser = globalThis.NagaParser;
const backend=globalThis.PaipuBackend, fetch=backend.request;
let serverState='starting';
function renderServerState(){const el=$('serverStatus');el.hidden=serverState==='ready';el.textContent=t(serverState==='failed'?'서버 준비에 시간이 걸립니다. 잠시 후 다시 시도해 주세요.':'변환 서버를 준비하고 있습니다. 링크를 붙여넣거나 JSON 파일을 먼저 사용할 수 있습니다.');}
document.addEventListener('paipu-server-state',e=>{serverState=e.detail;renderServerState();});
const i18n=globalThis.PaipuI18n, t=i18n.t;
let authSnapshot=null;
let retryUntil=0, retryTimer=0;
function updateConvertButton(){
 const btn=$('convertUrlBtn');
 const remaining=Math.max(0,Math.ceil((retryUntil-Date.now())/1000));
 btn.disabled=busy||remaining>0;
 if(busy){btn.textContent=t('작혼 패보를 가져오는 중…');return;}
 if(remaining){const time=remaining>=60?t('{n}분',{n:Math.ceil(remaining/60)}):t('{n}초',{n:remaining});btn.textContent=t('{time} 후 다시 시도',{time});return;}
 clearInterval(retryTimer);retryTimer=0;btn.textContent=t('불러오기');
}
function setReplayCooldown(data,response){
 const seconds=Number(data.retry_after||response.headers.get('Retry-After'));
 if(!Number.isFinite(seconds)||seconds<1||seconds>3600)return;
 retryUntil=Date.now()+Math.ceil(seconds)*1000;clearInterval(retryTimer);
 retryTimer=setInterval(updateConvertButton,1000);updateConvertButton();
}

let rounds = []; let chosen = new Set(); let mode = 'url'; let latestFile = ''; let busy = false;
let koreanServerReady = null; let authenticated = false; let sharedReady = false; let serviceSetup = false;
const operatorMode = new URL(location.href).searchParams.get('setup') === '1';
// Hidden entry is navigation only; server-side operator authorization is unchanged.
const openOperator=()=>location.assign((backend.origin||location.origin)+'/?setup=1');
document.addEventListener('keydown',event=>{if(event.altKey&&event.shiftKey&&event.code==='KeyA'){event.preventDefault();openOperator();}});
const brand=document.querySelector('.mark');
let holdTimer=0;
const cancelHold=()=>{clearTimeout(holdTimer);holdTimer=0;};
brand.addEventListener('pointerdown',event=>{if(event.button!==0)return;cancelHold();holdTimer=setTimeout(openOperator,2000);});
for(const event of ['pointerup','pointercancel','pointerleave'])brand.addEventListener(event,cancelHold);
brand.addEventListener('contextmenu',event=>event.preventDefault());
function alertError(message){const el=$('errorBox');el.textContent=message;el.hidden=false;}
function clearError(){$('errorBox').hidden=true;$('backendInfo').hidden=true;}
let toastTimer=0;
function toast(message){const el=$('toast');el.textContent=t(message);el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,3500);}
function switchTab(to){mode=to;clearError();const isUrl=to==='url';$('backendInfo').hidden=true;$('urlMode').hidden=!isUrl;$('fileMode').hidden=isUrl;$('urlTab').classList.toggle('active',isUrl);$('fileTab').classList.toggle('active',!isUrl);$('urlTab').setAttribute('aria-selected',String(isUrl));$('fileTab').setAttribute('aria-selected',String(!isUrl));}
function normalizeRecord(v){if(typeof v==='string'){try{return JSON.parse(v);}catch{throw new Error(t('서버가 올바른 JSON을 반환하지 않았습니다.'));}}
 if(v&&typeof v==='object'){for(const prop of ['tenhou','result','data','json','record','payload']){if(v[prop]&&typeof v[prop]==='object'&&Array.isArray(v[prop].log))return v[prop];}return v;}
 throw new Error(t('서버 응답에 천봉 JSON이 없습니다.'));}
function importData(data,title){try{const source=typeof data==='string'?data:JSON.stringify(normalizeRecord(data));const res=parser.parseText(source);if(!res.length)throw Error(t('대국 기록을 찾지 못했습니다.'));rounds=res;latestFile=title;chosen=new Set();$('inputPanel').hidden=false;$('roundPanel').hidden=false;$('resultPanel').hidden=true;$('matchTitle').textContent=t(title);$('totalRounds').textContent=String(rounds.length);let dataObj;try{dataObj=typeof data==='string'?JSON.parse(data):normalizeRecord(data);}catch{dataObj={};}let names=Array.isArray(dataObj?.name)?dataObj.name.join(' · '):'';$('matchNames').textContent=names;$('errorBox').hidden=true;renderRounds();$('roundPanel').scrollIntoView({behavior:'smooth',block:'start'});}
 catch(err){alertError(t('패보를 해석하지 못했습니다: ')+i18n.error(err.message));}}
function humanResult(str){if(str==='和了')return t('화료');if(str==='流局')return t('유국');if(str==='不明')return t('종료 기록 불명');return str||t('결과 미상');}
function renderRounds(){
 const box=$('roundList');box.replaceChildren();
 for(const r of rounds){
  const label=document.createElement('label');label.className='round-card'+(chosen.has(r.id)?' checked':'');
  const inp=document.createElement('input');inp.type='checkbox';inp.checked=chosen.has(r.id);inp.setAttribute('aria-label',i18n.roundName(r.roundNo,r.honba));
  inp.addEventListener('change',()=>{if(inp.checked)chosen.add(r.id);else chosen.delete(r.id);$('resultPanel').hidden=true;renderRounds();});
  const wind=document.createElement('span');const windIndex=Math.min(3,Math.floor(r.roundNo/4));wind.className='wind-badge wind-'+windIndex;wind.textContent=t(['동','남','서','북'][windIndex]);wind.setAttribute('aria-hidden','true');
  const name=document.createElement('strong');name.className='round-name';name.textContent=i18n.roundName(r.roundNo,r.honba);
  const sub=document.createElement('span');sub.className='round-result';const record=parser.parseUrlJSON(r.url);sub.textContent=parser.winSummary(record.log[0],record.name,i18n.language)||humanResult(r.result)+(r.incompleteWin?t(' · 점수 정보 부족'):'');
  label.append(inp,wind,name,sub);box.append(label);
 }
 const n=chosen.size;$('selectedCount').textContent=t('{n}국 선택',{n});$('summaryCount').textContent=String(n);$('costCount').textContent=String(n);$('generateBtn').disabled=n===0;
}
function setChosen(predicate){$('resultPanel').hidden=true;chosen=new Set(rounds.filter(predicate).map(v=>v.id));renderRounds();}
function buildOutput(){if(chosen.size===0)return;$('copyCheckInput').value='';$('copyCheckStatus').textContent='';let output=parser.urlsForSelection(rounds,chosen,$('anonymousCheck').checked);$('outputArea').value=output;updateTextView(output);$('roundPanel').hidden=false;$('resultPanel').hidden=false;$('resultSummary').textContent=t('✓ 선택한 {n}개 국의 URL을 만들었습니다.',{n:chosen.size});const selected=rounds.filter(v=>chosen.has(v.id));const incomplete=selected.filter(v=>v.incompleteWin).length;const recovered=selected.filter(v=>v.recoveredWin&&!v.incompleteWin).length;const notes=[];if(recovered)notes.push(t('{n}개 국의 타점을 원본 점수 증감에서 복원했습니다. 원본에 없는 부수·판수·역은 추가하지 않았습니다.',{n:recovered}));if(incomplete)notes.push(t("{n}개 국은 원본의 점수 정보가 부족하거나 특수 정산을 확정할 수 없어 종료 기록을 '不明'으로 표기했습니다.",{n:incomplete}));$('convertWarnings').hidden=!notes.length;$('convertWarnings').textContent=notes.join(' ');$('resultPanel').scrollIntoView({behavior:'smooth',block:'start'});}
async function readFile(f){clearError();if(!f)return;if(f.size>parser.MAX_BYTES){alertError(t('파일 크기는 10MB 이하여야 합니다.'));return;}try{const txt=await f.text();importData(txt,f.name);}catch(e){alertError(t('파일을 읽는 중 오류: ')+i18n.error(e.message));}}
function normalizedUrl(text) {
  return globalThis.MajsoulShare.extract(text);
}
function validUrl(text){try{normalizedUrl(text);return true;}catch{return false;}}

let queueSnapshot=null;
function renderQueue(data){
 queueSnapshot=data;$('queuePanel').hidden=false;
 $('queueTitle').textContent=data.state==='processing'?t('패보 처리 중'):t('대기열 {n}번째',{n:data.position||1});
 $('queueOverview').textContent=t('대기 {waiting}건 · 처리 중 {processing}건',{
  waiting:data.waiting_count??0,processing:data.processing_count??0});
 $('queueDetail').textContent=data.state==='processing'?t('작혼 패보를 가져와 변환하고 있습니다.'):
  (data.cooldown?t('작혼 조회 제한으로 잠시 쉬는 중입니다. 접수된 순서대로 자동 처리합니다.'):
  data.retrying?t('연결되지 않는 조회 계정을 건너뛰고 다른 계정으로 다시 시도합니다.'):
  t('전체 분당 10회로 순서대로 처리합니다. 다시 누르지 않아도 됩니다.'))+
  (data.wait_seconds>0?' '+t('조회 간격 대기: {n}초 이상',{n:data.wait_seconds}):'');
 $('convertUrlBtn').textContent=data.state==='processing'?t('패보 처리 중'):t('대기열 {n}번째',{n:data.position||1});
}
async function replayResponse(response){
 const data=await response.json().catch(()=>({}));
 if(!response.ok){
  if(response.status===429||response.status===503)setReplayCooldown(data,response);
  if(response.status===401)await refreshAuth();
  throw Error(apiError(data,response.status));
 }
 return data;
}
async function loadFromUrl(){
 if(busy||Date.now()<retryUntil)return;
 clearError();let value;
 try{value=normalizedUrl($('paipuInput').value);}catch(e){alertError(i18n.error(e.message));return;}
 busy=true;updateConvertButton();
 try{
  await backend.ready();
  const response=await fetch('/api/convert',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:value}),signal:AbortSignal.timeout(30000)});
  let data=await replayResponse(response);
  const deadline=Date.now()+35*60*1000;
  while(data.job){
   renderQueue(data);
   if(Date.now()>deadline)throw Error(t('대기 시간이 길어졌습니다. 잠시 후 다시 접수해 주세요.'));
   await new Promise(resolve=>setTimeout(resolve,Math.min(5,Math.max(2,Number(data.poll_after)||2))*1000));
   const poll=await fetch('/api/convert/status?job='+encodeURIComponent(data.job),{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(15000)});
   data=await replayResponse(poll);
  }
  importData(data,'작혼 공유 패보');
 }catch(e){
  const msg=e.name==='TimeoutError'||e.name==='AbortError'?t('서버 응답을 기다리는 중 연결이 끊겼습니다. 잠시 후 다시 접수해 주세요.'):i18n.error(e.message);
  if(e instanceof TypeError){$('backendDetail').textContent=t('변환 서버에 연결할 수 없습니다.');$('backendInfo').hidden=false;}
  alertError(msg);
 }finally{busy=false;queueSnapshot=null;$('queuePanel').hidden=true;updateConvertButton();}
}
async function copyOutput(){
 const el=$('outputArea');
 $('copyCheckInput').value='';$('copyCheckStatus').textContent='';
 const copied=await globalThis.PaipuClipboard.copyText(el.value,el);
 toast(copied?'NAGA용 URL을 복사했어요.':'자동 복사가 허용되지 않았습니다. 선택된 URL을 직접 복사해 주세요.');
 return copied;
}
function checkCopiedText(){
 const check=globalThis.PaipuClipboard.inspectPaste($('outputArea').value,$('copyCheckInput').value);
 const keys={match:'원문과 일치합니다. {n}개 URL의 줄바꿈이 유지됐습니다.',linebreaks:'줄바꿈이 사라졌습니다. 원본 {n}줄, 붙여넣기 {m}줄입니다.',changed:'복사한 내용이 원문과 다릅니다. 원본 {n}줄, 붙여넣기 {m}줄입니다.'};
 $('copyCheckStatus').textContent=check.state==='empty'?'':t(keys[check.state],{n:check.expectedLines,m:check.actualLines});
}
$('copyCheckInput').addEventListener('input',checkCopiedText);
// iPhone users copy the visible text themselves; never overwrite that clipboard.
$('automaticCopyActions').hidden=globalThis.PaipuClipboard.isIOS();
$('automaticCopyExtras').hidden=globalThis.PaipuClipboard.isIOS();
let textViewUrl=null;
function updateTextView(text){
 if(textViewUrl)URL.revokeObjectURL(textViewUrl);
 textViewUrl=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));
 $('textViewLink').href=textViewUrl;
}
function saveJSON(){
 const selected=parser.jsonForSelection(rounds,chosen,$('anonymousCheck').checked);
 const blob=new Blob([JSON.stringify(selected.length===1?selected[0]:selected,null,2)],{type:'application/json;charset=utf-8'});
 const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='PAIPU_selected_rounds.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function openNaga(){
 // Keep focus until copying finishes. Same-tab navigation also works after
 // asynchronous permission checks on browsers which block delayed popups.
 // Never access NAGA cookies or call its analysis/charge API.
 if(!await copyOutput())return false;
 location.assign('https://naga.dmv.nico/naga_report/order_form/?show_tab=1');
 return true;
}
function saveOutput(){const url=URL.createObjectURL(new Blob([$('outputArea').value],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='NAGA_selected_rounds.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
window.addEventListener('pagehide',()=>{$('operatorKeyInput').value='';});
$('nagaBtn').onclick=openNaga;
$('jsonDownloadBtn').onclick=saveJSON;
$('urlTab').onclick=()=>switchTab('url');$('fileTab').onclick=()=>switchTab('file');$('convertUrlBtn').onclick=loadFromUrl;$('jsonInput').onchange=e=>readFile(e.target.files?.[0]);const zone=$('dropzone');zone.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('jsonInput').click();}};zone.ondragover=e=>{e.preventDefault();zone.classList.add('hover');};zone.ondragleave=()=>zone.classList.remove('hover');zone.ondrop=e=>{e.preventDefault();zone.classList.remove('hover');readFile(e.dataTransfer?.files?.[0]);};
$('resetBtn').onclick=()=>{$('inputPanel').hidden=false;$('roundPanel').hidden=true;$('resultPanel').hidden=true;clearError();$('inputPanel').scrollIntoView({behavior:'smooth'});};$('allBtn').onclick=()=>setChosen(()=>true);$('noneBtn').onclick=()=>setChosen(()=>false);$('eastBtn').onclick=()=>setChosen(r=>r.roundNo<4);$('southBtn').onclick=()=>setChosen(r=>r.roundNo>=4&&r.roundNo<8);$('generateBtn').onclick=buildOutput;$('copyBtn').onclick=copyOutput;$('downloadBtn').onclick=saveOutput;$('editBtn').onclick=()=>{$('resultPanel').hidden=true;$('roundPanel').hidden=false;};
// Server-backed Yostar authentication; no passwords and no session token in JS storage.
function apiError(data,status){
 if(data.code==='UPSTREAM_REPLAY_LIMITED')return t('작혼의 패보 조회 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.');
 if(data.code==='REPLAY_QUEUE_EXPIRED')return t('대기 요청이 만료되었거나 서버가 재시작됐습니다. 다시 접수해 주세요.');
 if(data.code==='REPLAY_QUEUE_FULL')return t('대기열이 가득 찼습니다. 잠시 후 다시 접수해 주세요.');
 if(data.code==='REPLAY_ALREADY_QUEUED')return t('이미 접수한 패보를 처리 중입니다. 완료 후 다른 패보를 접수해 주세요.');
 if(data.code==='REPLAY_BUSY')return t('현재 다른 패보를 처리 중입니다. 잠시 후 다시 시도해 주세요.');
 if(data.code==='VISITOR_RATE_LIMITED')return t('짧은 시간에 요청이 많았습니다. 버튼의 대기 시간이 끝나면 다시 이용할 수 있습니다.');
 if(data.code==='SERVICE_RATE_LIMITED')return t('현재 패보 조회가 몰리고 있습니다. 버튼의 대기 시간이 끝나면 다시 시도해 주세요.');
 const message=i18n.error(data.error||t('요청에 실패했습니다. 잠시 후 다시 시도해 주세요.'));
 const code=typeof data.code==='string'&&/^[A-Z_]+$/.test(data.code)?data.code:'';
 return message+` (HTTP ${status}${code?' · '+code:''}${Number.isInteger(data.server_code)&&data.server_code?' · '+data.server_code:''})`;
}
async function api(path, value={}) {
  const res=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json',...(serviceSetup?{'X-Paipu-Operator-Key':$('operatorKeyInput').value}:{})},body:JSON.stringify(value)});
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw Error(apiError(data,res.status));
  return data;
}
async function refreshAuth(){
  try{
    const res=await fetch('/api/auth/status',{credentials:'same-origin',cache:'no-store'});
    const data=await res.json();
    authSnapshot=data;renderAuth(data);
  }catch(e){authenticated=false;$('backendDetail').textContent=t('계정 연결 상태를 확인하지 못했습니다. 페이지를 새로고침해 주세요.');$('backendInfo').hidden=false;}
}
function renderAuth(data){
    authenticated=!!data.authenticated;
    sharedReady=!!data.shared_ready;
    serviceSetup=operatorMode&&!!data.shared_configured;
    $('personalEmailFields').hidden=serviceSetup;
    $('operatorAccess').hidden=!serviceSetup;
    $('sendCodeBtn').textContent=serviceSetup?t('공용 계정 인증 메일 발송'):t('인증 메일 발송');
    $('sharedReady').hidden=true;
    $('sharedSetup').hidden=!operatorMode||!data.shared_configured;
    $('authPanel').hidden=!operatorMode;
    if(data.shared_configured){
      const storageText=data.shared_session_storage==='encrypted_postgres'
        ? t(' 인증 정보는 외부 DB에 암호화 저장되며 서버 재시작 후 복원됩니다.')
        : data.shared_session_storage==='encrypted_file'
        ? t(' 세션은 서버의 암호화 저장 파일에서 복원됩니다.')
        : t(' 현재 메모리 저장 모드이므로 서버 재시작 후에는 운영자 재인증이 필요합니다.');
      $('sharedSetupDetail').textContent=operatorMode
        ? t('서버에 지정한 공용 계정 이메일로 인증하면 방문자가 로그인 없이 패보를 조회할 수 있습니다.')+storageText
        : t('공용 계정의 최초 인증 또는 재인증이 필요합니다. 운영자 설정 화면에서 연결해 주세요.');
      if(data.shared_storage_available===false)$('sharedSetupDetail').textContent=t('인증 저장소에 연결할 수 없습니다. 인증 정보는 보존되어 있으며 서버의 저장소 설정 확인이 필요합니다. JSON 업로드는 계속 사용할 수 있습니다.');
      if(operatorMode)$('authInfo').textContent=t('지정된 공용 계정만 등록됩니다. 일반 방문자에게 이메일·토큰은 공개되지 않습니다. 인증이 만료되면 운영자가 다시 인증해야 합니다.');
    }
    $('accountSlotField').hidden=!serviceSetup;
    if(serviceSetup){
      const selected=$('accountSlot').value;
      $('accountSlot').replaceChildren();
      for(const account of data.shared_accounts||[{slot:1,ready:sharedReady}]){
        const option=document.createElement('option');option.value=String(account.slot);
        option.textContent=t('조회 계정 {n}',{n:account.slot})+' · '+String(account.region||'kr').toUpperCase()+' · '+(account.ready?t('연결됨'):t('최초 인증 필요'))+(account.cooling?' · '+t('일시 휴식 중'):'');
        $('accountSlot').append(option);
      }
      if([...$('accountSlot').options].some(o=>o.value===selected))$('accountSlot').value=selected;
    }
    $('authLoggedOut').hidden=authenticated&&!serviceSetup;
    $('authLoggedIn').hidden=!authenticated||serviceSetup;
    $('signedInEmail').textContent=(data.email||t('로그인됨'))+' · '+String(data.region||'kr').toUpperCase();
    if(authenticated){$('regionSelect').value=data.region||'kr';$('regionSelect').disabled=true;}else{$('regionSelect').disabled=serviceSetup;}
    if(serviceSetup){const selected=(data.shared_accounts||[]).find(a=>String(a.slot)===$('accountSlot').value);if(selected)$('regionSelect').value=selected.region||'kr';}
    $('authStatus').textContent=operatorMode&&data.shared_configured?(sharedReady?t('공용 조회 계정 연결됨'):t('공용 계정 최초 인증 필요')):authenticated?(data.game_authenticated?t('게임 로그인 및 패보 조회 확인됨'):t('이메일 인증 완료 · 게임 로그인은 조회 시 확인')):t('작혼 패보를 읽기 위한 이메일 인증');
}
function authError(e){alertError(i18n.error(e.message));$('authPanel').scrollIntoView({behavior:'smooth',block:'center'});}
$('sendCodeBtn').onclick=async()=>{
  const btn=$('sendCodeBtn');btn.disabled=true;
  clearError();btn.textContent=t('발송 중…');
  try{
    await api('/api/auth/send-code',serviceSetup?{service_account:true,account_slot:Number($('accountSlot').value)}:{email:$('emailInput').value.trim(),region:$('regionSelect').value});
    $('verifyRow').hidden=false;toast('Yostar 인증 메일을 확인해 주세요.');$('codeInput').focus();
  }catch(e){authError(e);}
  finally{btn.disabled=false;btn.textContent=serviceSetup?t('공용 계정 인증 메일 발송'):t('인증 메일 발송');}
};
let accountSnapshot=null;
function renderAccounts(data){
 accountSnapshot=data;
 const email=slot=>data.accounts.find(a=>a.slot===slot)?.email||t('없음');
 const lines=[t('현재 처리 계정: {email}',{email:email(data.active_slot)}),
  t('최근 조회 계정: {email}',{email:email(data.last_used_slot)}),
  t('최근 성공 계정: {email}',{email:email(data.last_success_slot)}),
  t('다음 조회 계정: {email}',{email:email(data.next_slot)})];
 for(const a of data.accounts){
  const state=!a.authenticated?t('최초 인증 필요'):a.unavailable_reason?t('게임 로그인 확인 필요')+' ('+a.unavailable_reason+')':
   a.cooldown_seconds>0?t('휴식 {n}초',{n:a.cooldown_seconds}):
   a.rate_limit_count>0?t('조회 제한(540) 이력 · 재시도 가능'):a.last_success_at?t('패보 조회 성공 확인'):t('인증 완료 · 조회 확인 전');
  lines.push(t('조회 계정 {n}',{n:a.slot})+' · '+a.email+' · '+a.region.toUpperCase()+' · '+state);
 }
 $('accountSlotStatus').textContent=lines.join('\n');
 const date=value=>value?new Intl.DateTimeFormat({ko:'ko-KR',en:'en-GB',ja:'ja-JP'}[i18n.language],{timeZone:'Asia/Seoul',dateStyle:'short',timeStyle:'short'}).format(new Date(value*1000)):t('없음');
 $('accountUsage').hidden=false;
 $('usageInfo').textContent=(data.usage_started_at?t('집계 시작: {time} · 한국시간 기준',{time:date(data.usage_started_at)}):t('첫 조회부터 집계됩니다.'))+' '+t('캐시 재사용·대기열 확인·이메일 인증은 제외됩니다. 성공·실패는 처리 완료일 기준입니다.')+(data.usage_persistent?'':' '+t('메모리 통계: 서버 재시작 시 초기화됩니다.'));
 $('usageCards').replaceChildren();
 for(const a of data.accounts){
  const card=document.createElement('article');card.className='usage-card';
  const title=document.createElement('strong');title.textContent=t('조회 계정 {n}',{n:a.slot})+' · '+a.email;card.append(title);
  const table=document.createElement('table');
  const header=table.createTHead().insertRow();
  for(const label of ['기간','조회 시도','성공','실패']){const th=document.createElement('th');th.scope='col';th.textContent=t(label);header.append(th);}
  const body=table.createTBody();
  for(const [key,label] of [['today','오늘'],['total','전체']]){const row=body.insertRow();const th=document.createElement('th');th.scope='row';th.textContent=t(label);row.append(th);for(const metric of ['attempts','successes','failures']){row.insertCell().textContent=String(a.usage?.[key]?.[metric]??0);}}
  card.append(table);
  const detail=document.createElement('p');detail.className='hint';detail.textContent=t('최근 시도: {time}',{time:date(a.usage?.last_attempt_at)})+' · '+t('진행 중·결과 미확인: {n}',{n:a.usage?.unfinished??0});
  if(a.usage?.last_failure_at)detail.textContent+=' · '+t('최근 실패: {time}',{time:date(a.usage.last_failure_at)})+(Number.isInteger(a.usage.last_error_code)?' ('+a.usage.last_error_code+')':'');
  card.append(detail);$('usageCards').append(card);
 }
}
async function refreshAccounts(){
 if(!serviceSetup)return;
 try{renderAccounts(await api('/api/auth/accounts'));}catch(e){authError(e);}
}
$('accountStatusBtn').onclick=refreshAccounts;
$('accountSlot').onchange=()=>{$('verifyRow').hidden=true;$('codeInput').value='';clearError();const selected=(authSnapshot?.shared_accounts||[]).find(a=>String(a.slot)===$('accountSlot').value);if(selected)$('regionSelect').value=selected.region||'kr';};
$('verifyBtn').onclick=async()=>{
  const btn=$('verifyBtn');btn.disabled=true;btn.textContent=t('인증 중…');clearError();
  try{
    await api('/api/auth/verify',{code:$('codeInput').value.trim()});
    $('codeInput').value='';await refreshAuth();if(serviceSetup)await refreshAccounts();toast('인증 성공.');
    if(!serviceSetup && $('paipuInput').value.trim() && validUrl($('paipuInput').value))await loadFromUrl();
  }catch(e){authError(e);}
  finally{btn.disabled=false;btn.textContent=t('로그인');}
};
$('logoutBtn').onclick=async()=>{
  try{await api('/api/auth/logout');await refreshAuth();toast('로그아웃했습니다.');}
  catch(e){authError(e);}
};
async function detectKoreanProvider(){
  try{
    const data=await backend.ready();
    $('buildVersion').textContent=` · ${data.version||''} · ${(data.build_commit||'local').slice(0,7)}`;
    koreanServerReady=data.kr_fetch_available===true;
    if(!koreanServerReady){$('backendDetail').textContent=t('패보 변환 라이브러리 로딩에 실패했습니다. 서버 설치 상태를 확인해 주세요.');$('backendInfo').hidden=false;}
    await refreshAuth();
  }catch(e){$('backendDetail').textContent=t('패보 서버가 실행되고 있지 않습니다. 웹서버로 사이트를 열어야 합니다.');$('backendInfo').hidden=false;}
}
document.addEventListener('paipu-language-change',()=>{
 clearError();$('toast').hidden=true;renderServerState();
 if(authSnapshot)renderAuth(authSnapshot);
 updateConvertButton();
 if(queueSnapshot)renderQueue(queueSnapshot);
 if(accountSnapshot)renderAccounts(accountSnapshot);
 if(!$('verifyBtn').disabled)$('verifyBtn').textContent=t('로그인');
 if(rounds.length){renderRounds();$('matchTitle').textContent=t(latestFile);if(!$('resultPanel').hidden)buildOutput();}
});
detectKoreanProvider();
// Support opening this website with a replay ID in the page URL, e.g.
// https://host.example/?paipu=261014-xxx_a123. No conversion is claimed without a provider.
const externalPaipu = new URL(location.href).searchParams.get('paipu');
if (externalPaipu && /^[A-Za-z0-9_-]{12,160}$/.test(externalPaipu)) {
  $('paipuInput').value='https://game.mahjongsoul.com/?paipu='+externalPaipu;
}
// Allow an external converter to link directly to this page with a Tenhou JSON URL in the hash.
// Never auto-submit a NAGA request (NP charge).
if(location.hash.startsWith('#json=')){try{const encoded=location.hash.slice(6);const parsed=JSON.parse(decodeURIComponent(encoded));importData(parsed,'천봉 URL 패보');}catch(e){alertError(t('URL JSON을 읽을 수 없습니다: ')+i18n.error(e.message));}}
})();

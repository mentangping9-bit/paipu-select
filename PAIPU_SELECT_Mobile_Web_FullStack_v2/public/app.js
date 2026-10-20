(() => {
'use strict';
const $ = id => document.getElementById(id);
const parser = globalThis.NagaParser;
const i18n=globalThis.PaipuI18n, t=i18n.t;
let authSnapshot=null;
let rounds = []; let chosen = new Set(); let mode = 'url'; let latestFile = ''; let busy = false;
let koreanServerReady = null; let authenticated = false; let sharedReady = false; let serviceSetup = false;
const operatorMode = new URL(location.href).searchParams.get('setup') === '1';
function alertError(message){const el=$('errorBox');el.textContent=message;el.hidden=false;}
function clearError(){$('errorBox').hidden=true;$('backendInfo').hidden=true;}
let toastTimer=0;
function toast(message){const el=$('toast');el.textContent=t(message);el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,3500);}
function switchTab(to){mode=to;clearError();const isUrl=to==='url';$('backendInfo').hidden=true;$('urlMode').hidden=!isUrl;$('fileMode').hidden=isUrl;$('urlTab').classList.toggle('active',isUrl);$('fileTab').classList.toggle('active',!isUrl);$('urlTab').setAttribute('aria-selected',String(isUrl));$('fileTab').setAttribute('aria-selected',String(!isUrl));}
function normalizeRecord(v){if(typeof v==='string'){try{return JSON.parse(v);}catch{throw new Error(t('서버가 올바른 JSON을 반환하지 않았습니다.'));}}
 if(v&&typeof v==='object'){for(const prop of ['tenhou','result','data','json','record','payload']){if(v[prop]&&typeof v[prop]==='object'&&Array.isArray(v[prop].log))return v[prop];}return v;}
 throw new Error(t('서버 응답에 천봉 JSON이 없습니다.'));}
function importData(data,title){try{const source=typeof data==='string'?data:JSON.stringify(normalizeRecord(data));const res=parser.parseText(source);if(!res.length)throw Error(t('대국 기록을 찾지 못했습니다.'));rounds=res;latestFile=title;chosen=new Set();$('inputPanel').hidden=true;$('roundPanel').hidden=false;$('resultPanel').hidden=true;$('matchTitle').textContent=t(title);$('totalRounds').textContent=String(rounds.length);let dataObj;try{dataObj=typeof data==='string'?JSON.parse(data):normalizeRecord(data);}catch{dataObj={};}let names=Array.isArray(dataObj?.name)?dataObj.name.join(' · '):'';$('matchNames').textContent=names;$('errorBox').hidden=true;renderRounds();$('roundPanel').scrollIntoView({behavior:'smooth',block:'start'});}
 catch(err){alertError(t('패보를 해석하지 못했습니다: ')+i18n.error(err.message));}}
function humanResult(str){if(str==='和了')return t('화료');if(str==='流局')return t('유국');if(str==='不明')return t('종료 기록 불명');return str||t('결과 미상');}
function renderRounds(){const box=$('roundList');box.replaceChildren();for(const r of rounds){const on=chosen.has(r.id);const label=document.createElement('label');label.className='round-card'+(on?' checked':'');const inp=document.createElement('input');inp.type='checkbox';inp.checked=on;inp.setAttribute('aria-label',i18n.roundName(r.roundNo,r.honba));inp.addEventListener('change',()=>{if(inp.checked)chosen.add(r.id);else chosen.delete(r.id);renderRounds();});const tick=document.createElement('span');tick.className='checkmark';tick.textContent='✓';const info=document.createElement('span');info.className='round-meta';const name=document.createElement('strong');name.textContent=i18n.roundName(r.roundNo,r.honba);const sub=document.createElement('small');const record=parser.parseUrlJSON(r.url);sub.textContent=parser.winSummary(record.log[0],record.name,i18n.language)||humanResult(r.result)+(r.incompleteWin?t(' · 점수 정보 부족'):'');info.append(name,sub);label.append(inp,tick,info);box.append(label);}const n=chosen.size;$('selectedCount').textContent=t('{n}국 선택',{n});$('summaryCount').textContent=String(n);$('costCount').textContent=String(n);$('generateBtn').disabled=n===0;}
function setChosen(predicate){chosen=new Set(rounds.filter(predicate).map(v=>v.id));renderRounds();}
function buildOutput(){if(chosen.size===0)return;let output=parser.urlsForSelection(rounds,chosen,$('anonymousCheck').checked);$('outputArea').value=output;$('roundPanel').hidden=true;$('resultPanel').hidden=false;$('resultSummary').textContent=t('✓ 선택한 {n}개 국의 URL을 만들었습니다.',{n:chosen.size});const selected=rounds.filter(v=>chosen.has(v.id));const incomplete=selected.filter(v=>v.incompleteWin).length;const recovered=selected.filter(v=>v.recoveredWin&&!v.incompleteWin).length;const notes=[];if(recovered)notes.push(t('{n}개 국의 타점을 원본 점수 증감에서 복원했습니다. 원본에 없는 부수·판수·역은 추가하지 않았습니다.',{n:recovered}));if(incomplete)notes.push(t("{n}개 국은 원본의 점수 정보가 부족하거나 특수 정산을 확정할 수 없어 종료 기록을 '不明'으로 표기했습니다.",{n:incomplete}));$('convertWarnings').hidden=!notes.length;$('convertWarnings').textContent=notes.join(' ');$('resultPanel').scrollIntoView({behavior:'smooth',block:'start'});}
async function readFile(f){clearError();if(!f)return;if(f.size>parser.MAX_BYTES){alertError(t('파일 크기는 10MB 이하여야 합니다.'));return;}try{const txt=await f.text();importData(txt,f.name);}catch(e){alertError(t('파일을 읽는 중 오류: ')+i18n.error(e.message));}}
function normalizedUrl(text) {
  return globalThis.MajsoulShare.extract(text);
}
function validUrl(text){try{normalizedUrl(text);return true;}catch{return false;}}

async function loadFromUrl(){if(busy)return;clearError();let value;
try { value=normalizedUrl($('paipuInput').value); }
catch(e){alertError(i18n.error(e.message));return;}
// Keep the original pasted caption in the input so it is not lost.
 busy=true;const btn=$('convertUrlBtn');btn.disabled=true;btn.textContent=t('작혼 패보를 가져오는 중…');try{const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),110000);let response;try{response=await fetch('/api/convert',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:value}),signal:controller.signal});}finally{clearTimeout(timeout);}const data=await response.json().catch(()=>({}));if(!response.ok){if(response.status===401){await refreshAuth();const panel=$('authPanel').hidden?$('sharedSetup'):$('authPanel');panel.scrollIntoView({behavior:'smooth',block:'center'});toast(sharedReady?t('공용 계정 연결 상태를 확인해 주세요.'):apiError(data,response.status));}throw Error(apiError(data,response.status));}importData(data,'작혼 공유 패보');}catch(e){const msg=e.name==='AbortError'?t('110초 동안 서버 응답이 없습니다.'):i18n.error(e.message);if(e instanceof TypeError){$('backendDetail').textContent=t('변환 서버에 연결할 수 없습니다.');$('backendInfo').hidden=false;}alertError(msg);}finally{busy=false;btn.disabled=false;btn.textContent=t('패보 자동 변환하고 국 선택하기')+' →';}}
async function copyOutput(){
 const text=$('outputArea').value;
 try{await navigator.clipboard.writeText(text);toast('NAGA용 URL을 복사했어요.');return true;}
 catch{
  const el=$('outputArea');el.focus();el.select();el.setSelectionRange(0,text.length);
  try{if(document.execCommand('copy')){toast('URL을 복사했어요.');return true;}}catch{}
  toast('자동 복사가 허용되지 않았습니다. 선택된 URL을 직접 복사해 주세요.');return false;
 }
}
function saveJSON(){
 const selected=parser.jsonForSelection(rounds,chosen,$('anonymousCheck').checked);
 const blob=new Blob([JSON.stringify(selected.length===1?selected[0]:selected,null,2)],{type:'application/json;charset=utf-8'});
 const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='PAIPU_selected_rounds.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function openNaga(){
 // Open during the tap event, before awaiting clipboard permission on iOS.
 // Never access NAGA cookies or call its analysis/charge API.
 const copied=copyOutput(); // Request clipboard access while this tab still has focus.
 window.open('https://naga.dmv.nico/naga_report/order_form/','_blank','noopener,noreferrer');
 return copied;
}
function saveOutput(){const url=URL.createObjectURL(new Blob([$('outputArea').value],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='NAGA_selected_rounds.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('nagaBtn').onclick=openNaga;
$('jsonDownloadBtn').onclick=saveJSON;
$('urlTab').onclick=()=>switchTab('url');$('fileTab').onclick=()=>switchTab('file');$('convertUrlBtn').onclick=loadFromUrl;$('jsonInput').onchange=e=>readFile(e.target.files?.[0]);const zone=$('dropzone');zone.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('jsonInput').click();}};zone.ondragover=e=>{e.preventDefault();zone.classList.add('hover');};zone.ondragleave=()=>zone.classList.remove('hover');zone.ondrop=e=>{e.preventDefault();zone.classList.remove('hover');readFile(e.dataTransfer?.files?.[0]);};
$('resetBtn').onclick=()=>{$('inputPanel').hidden=false;$('roundPanel').hidden=true;$('resultPanel').hidden=true;clearError();$('inputPanel').scrollIntoView({behavior:'smooth'});};$('allBtn').onclick=()=>setChosen(()=>true);$('noneBtn').onclick=()=>setChosen(()=>false);$('eastBtn').onclick=()=>setChosen(r=>r.roundNo<4);$('southBtn').onclick=()=>setChosen(r=>r.roundNo>=4&&r.roundNo<8);$('generateBtn').onclick=buildOutput;$('copyBtn').onclick=copyOutput;$('downloadBtn').onclick=saveOutput;$('editBtn').onclick=()=>{$('resultPanel').hidden=true;$('roundPanel').hidden=false;};
// Server-backed Yostar authentication; no passwords and no session token in JS storage.
function apiError(data,status){
 const message=i18n.error(data.error||t('요청에 실패했습니다. 잠시 후 다시 시도해 주세요.'));
 const code=typeof data.code==='string'&&/^[A-Z_]+$/.test(data.code)?data.code:'';
 return message+` (HTTP ${status}${code?' · '+code:''}${Number.isInteger(data.server_code)&&data.server_code?' · '+data.server_code:''})`;
}
async function api(path, value={}) {
  const res=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
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
    $('sendCodeBtn').textContent=serviceSetup?t('공용 계정 인증 메일 발송'):t('인증 메일 발송');
    $('sharedReady').hidden=!sharedReady||operatorMode;
    $('sharedSetup').hidden=!data.shared_configured||(sharedReady&&!operatorMode);
    $('authPanel').hidden=!!data.shared_configured&&!operatorMode;
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
    $('authLoggedOut').hidden=authenticated;
    $('authLoggedIn').hidden=!authenticated;
    $('signedInEmail').textContent=(data.email||t('로그인됨'))+' · '+String(data.region||'kr').toUpperCase();
    if(authenticated){$('regionSelect').value=data.region||'kr';$('regionSelect').disabled=true;}else{$('regionSelect').disabled=serviceSetup;}
    $('authStatus').textContent=operatorMode&&data.shared_configured?(sharedReady?t('공용 조회 계정 연결됨'):t('공용 계정 최초 인증 필요')):authenticated?(data.game_authenticated?t('게임 로그인 및 패보 조회 확인됨'):t('이메일 인증 완료 · 게임 로그인은 조회 시 확인')):t('작혼 패보를 읽기 위한 이메일 인증');
}
function authError(e){alertError(i18n.error(e.message));$('authPanel').scrollIntoView({behavior:'smooth',block:'center'});}
$('sendCodeBtn').onclick=async()=>{
  const btn=$('sendCodeBtn');btn.disabled=true;
  clearError();btn.textContent=t('발송 중…');
  try{
    await api('/api/auth/send-code',serviceSetup?{service_account:true}:{email:$('emailInput').value.trim(),region:$('regionSelect').value});
    $('verifyRow').hidden=false;toast('Yostar 인증 메일을 확인해 주세요.');$('codeInput').focus();
  }catch(e){authError(e);}
  finally{btn.disabled=false;btn.textContent=serviceSetup?t('공용 계정 인증 메일 발송'):t('인증 메일 발송');}
};
$('verifyBtn').onclick=async()=>{
  const btn=$('verifyBtn');btn.disabled=true;btn.textContent=t('인증 중…');clearError();
  try{
    await api('/api/auth/verify',{code:$('codeInput').value.trim()});
    $('codeInput').value='';await refreshAuth();toast('인증 성공.');
    if($('paipuInput').value.trim() && validUrl($('paipuInput').value))await loadFromUrl();
  }catch(e){authError(e);}
  finally{btn.disabled=false;btn.textContent=t('로그인');}
};
$('logoutBtn').onclick=async()=>{
  try{await api('/api/auth/logout');await refreshAuth();toast('로그아웃했습니다.');}
  catch(e){authError(e);}
};
async function detectKoreanProvider(){
  try{
    const res=await fetch('/api/health',{cache:'no-store'});
    const data=await res.json();
    $('buildVersion').textContent=` · ${data.version||''} · ${(data.build_commit||'local').slice(0,7)}`;
    koreanServerReady=data.kr_fetch_available===true;
    if(!koreanServerReady){$('backendDetail').textContent=t('패보 변환 라이브러리 로딩에 실패했습니다. 서버 설치 상태를 확인해 주세요.');$('backendInfo').hidden=false;}
    await refreshAuth();
  }catch(e){$('backendDetail').textContent=t('패보 서버가 실행되고 있지 않습니다. 웹서버로 사이트를 열어야 합니다.');$('backendInfo').hidden=false;}
}
document.addEventListener('paipu-language-change',()=>{
 clearError();$('toast').hidden=true;
 if(authSnapshot)renderAuth(authSnapshot);
 if(!busy)$('convertUrlBtn').textContent=t('패보 자동 변환하고 국 선택하기')+' →';
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

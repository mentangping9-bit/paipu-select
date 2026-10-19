(() => {
'use strict';
const $ = id => document.getElementById(id);
const parser = globalThis.NagaParser;
let rounds = []; let chosen = new Set(); let mode = 'url'; let latestFile = ''; let busy = false;
let koreanServerReady = null; let authenticated = false;
function alertError(message){const el=$('errorBox');el.textContent=message;el.hidden=false;}
function clearError(){$('errorBox').hidden=true;$('backendInfo').hidden=true;}
let toastTimer=0;
function toast(message){const el=$('toast');el.textContent=message;el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,3500);}
function switchTab(to){mode=to;clearError();const isUrl=to==='url';$('backendInfo').hidden=true;$('urlMode').hidden=!isUrl;$('fileMode').hidden=isUrl;$('urlTab').classList.toggle('active',isUrl);$('fileTab').classList.toggle('active',!isUrl);$('urlTab').setAttribute('aria-selected',String(isUrl));$('fileTab').setAttribute('aria-selected',String(!isUrl));}
function normalizeRecord(v){if(typeof v==='string'){try{return JSON.parse(v);}catch{throw new Error('서버가 올바른 JSON을 반환하지 않았습니다.');}}
 if(v&&typeof v==='object'){for(const prop of ['tenhou','result','data','json','record','payload']){if(v[prop]&&typeof v[prop]==='object'&&Array.isArray(v[prop].log))return v[prop];}return v;}
 throw new Error('서버 응답에 천봉 JSON이 없습니다.');}
function importData(data,title){try{const source=typeof data==='string'?data:JSON.stringify(normalizeRecord(data));const res=parser.parseText(source);if(!res.length)throw Error('대국 기록을 찾지 못했습니다.');rounds=res;latestFile=title;chosen=new Set();$('inputPanel').hidden=true;$('roundPanel').hidden=false;$('resultPanel').hidden=true;$('matchTitle').textContent=title;$('totalRounds').textContent=String(rounds.length);let dataObj;try{dataObj=typeof data==='string'?JSON.parse(data):normalizeRecord(data);}catch{dataObj={};}let names=Array.isArray(dataObj?.name)?dataObj.name.join(' · '):'';$('matchNames').textContent=names;$('errorBox').hidden=true;renderRounds();$('roundPanel').scrollIntoView({behavior:'smooth',block:'start'});}
 catch(err){alertError('패보를 해석하지 못했습니다: '+err.message);}}
function humanResult(str){if(str==='和了')return '화료';if(str==='流局')return '유국';if(str==='不明')return '종료 기록 불명';return str||'결과 미상';}
function renderRounds(){const box=$('roundList');box.replaceChildren();for(const r of rounds){const on=chosen.has(r.id);const label=document.createElement('label');label.className='round-card'+(on?' checked':'');const inp=document.createElement('input');inp.type='checkbox';inp.checked=on;inp.setAttribute('aria-label',r.label+(r.honba?` ${r.honba}본장`:''));inp.addEventListener('change',()=>{if(inp.checked)chosen.add(r.id);else chosen.delete(r.id);renderRounds();});const tick=document.createElement('span');tick.className='checkmark';tick.textContent='✓';const info=document.createElement('span');info.className='round-meta';const name=document.createElement('strong');name.textContent=r.label+(r.honba?` ${r.honba}본장`:'');const sub=document.createElement('small');sub.textContent=humanResult(r.result)+(r.incompleteWin?' · 종료 결과 간략화':'');info.append(name,sub);label.append(inp,tick,info);box.append(label);}const n=chosen.size;$('selectedCount').textContent=n+'국 선택';$('summaryCount').textContent=String(n);$('costCount').textContent=String(n);$('generateBtn').disabled=n===0;}
function setChosen(predicate){chosen=new Set(rounds.filter(predicate).map(v=>v.id));renderRounds();}
function buildOutput(){if(chosen.size===0)return;let output=parser.urlsForSelection(rounds,chosen,$('anonymousCheck').checked);$('outputArea').value=output;$('roundPanel').hidden=true;$('resultPanel').hidden=false;$('resultSummary').textContent=`✓ 선택한 ${chosen.size}개 국의 URL을 만들었습니다.`;const incomplete=rounds.filter(v=>chosen.has(v.id)&&v.incompleteWin).length;$('convertWarnings').hidden=!incomplete;if(incomplete)$('convertWarnings').textContent=`${incomplete}개 국의 화료 점수·역 상세 정보가 원본에 없어 종국 결과를 '不明'으로 표기했습니다. NAGA 승인 여부는 제출 화면에서 확인해 주세요.`;$('resultPanel').scrollIntoView({behavior:'smooth',block:'start'});}
async function readFile(f){clearError();if(!f)return;if(f.size>parser.MAX_BYTES){alertError('파일 크기는 10MB 이하여야 합니다.');return;}try{const txt=await f.text();importData(txt,f.name);}catch(e){alertError('파일을 읽는 중 오류: '+e.message);}}
function normalizedUrl(text) {
  return globalThis.MajsoulShare.extract(text);
}
function validUrl(text){try{normalizedUrl(text);return true;}catch{return false;}}

async function loadFromUrl(){if(busy)return;clearError();let value;
try { value=normalizedUrl($('paipuInput').value); }
catch(e){alertError(e.message);return;}
// Keep the original pasted caption in the input so it is not lost.
 busy=true;const btn=$('convertUrlBtn');btn.disabled=true;btn.textContent='작혼 패보를 가져오는 중…';try{const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),110000);let response;try{response=await fetch('/api/convert',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:value}),signal:controller.signal});}finally{clearTimeout(timeout);}const data=await response.json().catch(()=>({}));if(!response.ok){if(response.status===401){$('authPanel').scrollIntoView({behavior:'smooth',block:'center'});toast('먼저 Yostar 이메일 인증을 완료하세요.');}throw Error(data.error||`서버 오류 HTTP ${response.status}`);}importData(data,'작혼 공유 패보');}catch(e){const msg=e.name==='AbortError'?'110초 동안 서버 응답이 없습니다.':e.message;if(e instanceof TypeError){$('backendDetail').textContent='변환 서버에 연결할 수 없습니다.';$('backendInfo').hidden=false;}alertError(msg);}finally{busy=false;btn.disabled=false;btn.innerHTML='패보 자동 변환하고 국 선택하기 <span class="arrow-icon">→</span>';}}
async function copyOutput(){const text=$('outputArea').value;try{await navigator.clipboard.writeText(text);toast('NAGA용 URL을 복사했어요.');}catch{const el=$('outputArea');el.focus();el.select();try{document.execCommand('copy');toast('URL을 복사했어요.');}catch{toast('복사할 URL을 길게 눌러 선택해 주세요.');}}}
function saveOutput(){const url=URL.createObjectURL(new Blob([$('outputArea').value],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='NAGA_selected_rounds.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('urlTab').onclick=()=>switchTab('url');$('fileTab').onclick=()=>switchTab('file');$('convertUrlBtn').onclick=loadFromUrl;$('jsonInput').onchange=e=>readFile(e.target.files?.[0]);const zone=$('dropzone');zone.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('jsonInput').click();}};zone.ondragover=e=>{e.preventDefault();zone.classList.add('hover');};zone.ondragleave=()=>zone.classList.remove('hover');zone.ondrop=e=>{e.preventDefault();zone.classList.remove('hover');readFile(e.dataTransfer?.files?.[0]);};
$('resetBtn').onclick=()=>{$('inputPanel').hidden=false;$('roundPanel').hidden=true;$('resultPanel').hidden=true;clearError();$('inputPanel').scrollIntoView({behavior:'smooth'});};$('allBtn').onclick=()=>setChosen(()=>true);$('noneBtn').onclick=()=>setChosen(()=>false);$('eastBtn').onclick=()=>setChosen(r=>r.roundNo<4);$('southBtn').onclick=()=>setChosen(r=>r.roundNo>=4&&r.roundNo<8);$('generateBtn').onclick=buildOutput;$('copyBtn').onclick=copyOutput;$('downloadBtn').onclick=saveOutput;$('editBtn').onclick=()=>{$('resultPanel').hidden=true;$('roundPanel').hidden=false;};
// Server-backed Yostar authentication; no passwords and no session token in JS storage.
async function api(path, value={}) {
  const res=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw Error(data.error||'서버 오류: '+res.status);
  return data;
}
async function refreshAuth(){
  try{
    const res=await fetch('/api/auth/status',{credentials:'same-origin',cache:'no-store'});
    const data=await res.json();
    authenticated=!!data.authenticated;
    $('authLoggedOut').hidden=authenticated;
    $('authLoggedIn').hidden=!authenticated;
    $('signedInEmail').textContent=data.email||'로그인됨';
    $('authStatus').textContent=authenticated?'Yostar 이메일 인증 완료 · 패보 조회 준비':'작혼 패보를 읽기 위한 이메일 인증';
  }catch(e){authenticated=false;}
}
function authError(e){alertError(e.message);$('authPanel').scrollIntoView({behavior:'smooth',block:'center'});}
$('sendCodeBtn').onclick=async()=>{
  const btn=$('sendCodeBtn');btn.disabled=true;
  clearError();btn.textContent='발송 중…';
  try{
    await api('/api/auth/send-code',{email:$('emailInput').value.trim()});
    $('verifyRow').hidden=false;toast('Yostar 인증 메일을 확인해 주세요.');$('codeInput').focus();
  }catch(e){authError(e);}
  finally{btn.disabled=false;btn.textContent='인증 메일 발송';}
};
$('verifyBtn').onclick=async()=>{
  const btn=$('verifyBtn');btn.disabled=true;btn.textContent='인증 중…';clearError();
  try{
    await api('/api/auth/verify',{code:$('codeInput').value.trim()});
    $('codeInput').value='';await refreshAuth();toast('인증 성공.');
    if($('paipuInput').value.trim() && validUrl($('paipuInput').value))await loadFromUrl();
  }catch(e){authError(e);}
  finally{btn.disabled=false;btn.textContent='로그인';}
};
$('logoutBtn').onclick=async()=>{
  try{await api('/api/auth/logout');await refreshAuth();toast('로그아웃했습니다.');}
  catch(e){authError(e);}
};
async function detectKoreanProvider(){
  try{
    const res=await fetch('/api/health',{cache:'no-store'});
    const data=await res.json();
    koreanServerReady=data.kr_fetch_available===true;
    if(!koreanServerReady){$('backendDetail').textContent='패보 변환 라이브러리 로딩에 실패했습니다. 서버 설치 상태를 확인해 주세요.';$('backendInfo').hidden=false;}
    await refreshAuth();
  }catch(e){$('backendDetail').textContent='패보 서버가 실행되고 있지 않습니다. 웹서버로 사이트를 열어야 합니다.';$('backendInfo').hidden=false;}
}
detectKoreanProvider();
// Support opening this website with a replay ID in the page URL, e.g.
// https://host.example/?paipu=261014-xxx_a123. No conversion is claimed without a provider.
const externalPaipu = new URL(location.href).searchParams.get('paipu');
if (externalPaipu && /^[A-Za-z0-9_-]{12,160}$/.test(externalPaipu)) {
  $('paipuInput').value='https://game.mahjongsoul.com/?paipu='+externalPaipu;
}
// Allow an external converter to link directly to this page with a Tenhou JSON URL in the hash.
// Never auto-submit a NAGA request (NP charge).
if(location.hash.startsWith('#json=')){try{const encoded=location.hash.slice(6);const parsed=JSON.parse(decodeURIComponent(encoded));importData(parsed,'천봉 URL 패보');}catch(e){alertError('URL JSON을 읽을 수 없습니다: '+e.message);}}
})();

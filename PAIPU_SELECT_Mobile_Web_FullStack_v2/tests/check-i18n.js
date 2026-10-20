// Language changes must preserve replay data, selected IDs and payment amounts.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const publicDir=path.join(__dirname,'../public');
const html=fs.readFileSync(path.join(publicDir,'index.html'),'utf8');
const storage=new Map();
function load(browserLanguage='ko-KR',denyStorage=false){
  const nodes=[...html.matchAll(/>([^<>]+)</g)].map(m=>({nodeValue:m[1],parentElement:{tagName:'SPAN'},isConnected:true}));
  const attributes=[];
  for(const m of html.matchAll(/(?:placeholder|aria-label|content)="([^"]*)"/g))attributes.push(m[1]);
  const picker={value:'',addEventListener(){}};
  const context={navigator:{language:browserLanguage},NodeFilter:{SHOW_TEXT:4},Event:class{constructor(type){this.type=type;}},
    localStorage:{getItem:k=>{if(denyStorage)throw Error('blocked');return storage.get(k);},setItem:(k,v)=>{if(denyStorage)throw Error('blocked');storage.set(k,v);}},
    document:{documentElement:{lang:'ko'},createTreeWalker(){let i=-1;return {nextNode(){return ++i<nodes.length;},get currentNode(){return nodes[i];}};},
      querySelectorAll(){return [];},getElementById(){return picker;},dispatchEvent(){}},
  };
  context.globalThis=context;vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(publicDir,'i18n.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(publicDir,'converter.js'),'utf8'),context);
  return {context,nodes,attributes,I:context.PaipuI18n,P:context.NagaParser};
}
let {context,nodes,attributes,I,P}=load();
// Catch untranslated visible Korean text and accessibility/placeholder attributes.
for(const text of [...nodes.map(n=>n.nodeValue.trim()),...attributes]){
  if(/[가-힣]/.test(text)&&!['한국어','Language / 언어 / 言語'].includes(text))assert.ok(I.messages[text],`Missing translation: ${text}`);
}
const record=JSON.parse(fs.readFileSync(process.argv[2]||path.join(__dirname,'fixture.json'),'utf8'));
const source=JSON.stringify(record),rounds=P.parseText(source),ids=new Set(rounds.filter(r=>r.roundNo<4).map(r=>r.id));
const original=P.urlsForSelection(rounds,ids,false);
for(const language of ['ja','en','ko','en','ja']){
  I.setLanguage(language);
  assert.equal(context.document.documentElement.lang,language);
  assert.equal(P.urlsForSelection(rounds,ids,false),original,'Language changed replay payload or selection');
  assert.equal(JSON.stringify(record),source);
  assert.ok(nodes.some(n=>n.nodeValue.includes(I.t('패보 불러오기'))));
  for(const r of rounds){
    const d=P.parseUrlJSON(r.url),summary=P.winSummary(d.log[0],d.name,language);
    const withoutNames=(d.name||[]).reduce((text,name)=>text.replaceAll(name,''),summary);
    if(language!=='ko')assert.ok(!/[가-힣]/.test(withoutNames),summary);
  }
}
assert.equal(I.roundName(4,2),'南1局 2本場');
I.setLanguage('en');assert.equal(I.roundName(4,2),'South 1 · 2 honba');
assert.equal(I.t('{n}국 선택',{n:5}),'5 selected');
assert.equal(I.error('복사한 내용에서 공식 작혼 패보 링크를 찾지 못했습니다. 공유 문구 전체를 붙여넣어도 됩니다.'),'No official Mahjong Soul replay link found. You can paste the entire share text.');
assert.equal(load('ja-JP').I.language,'en','Saved preference lost on a new page');
storage.clear();assert.equal(load('ja-JP').I.language,'ja');
assert.doesNotThrow(()=>load('en-US',true).I.setLanguage('ja'));
const prior=I.language;I.setLanguage('invalid');assert.equal(I.language,prior);
const doubleRon=JSON.parse(JSON.stringify(record.log[0]));
doubleRon[0]=[0,1,0];doubleRon[16]=['和了',[-8000,10000,0,0],[1,0,1,'30符4飜7700点'],[-8000,0,8000,0],[2,0,2,'満貫8000点']];
const doubleSummary=P.winSummary(doubleRon,['A','B','C','D'],'en');
assert.ok(doubleSummary.includes('B Ron 7,700 points'));
assert.ok(doubleSummary.includes('C Ron 8,000 points'));
console.log('PASS: 3-language UI coverage, repeated switching, saved preference, storage failure, honba labels, unchanged replay payloads and payments');

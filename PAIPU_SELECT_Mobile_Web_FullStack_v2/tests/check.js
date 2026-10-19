const fs=require('node:fs');const vm=require('node:vm');const assert=require('node:assert/strict');const path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../public/converter.js'),'utf8');const ctx={};ctx.globalThis=ctx;vm.createContext(ctx);vm.runInContext(code,ctx);const P=ctx.NagaParser;
function test(actual, expected){assert.equal(actual,expected);}
const data=JSON.parse(fs.readFileSync(process.argv[2]||path.join(__dirname,'fixture.json'),'utf8'));
const rounds=P.parseText(JSON.stringify(data));test(rounds.length,data.log.length);
const honors=rounds.filter(r=>r.honba>0).length;console.log('국 개수:',rounds.length,'본장 발생:',honors);
let unknown=0;
for(let idx=0;idx<rounds.length;idx++){
 const src=data.log[idx];const got=P.parseUrlJSON(rounds[idx].url);
 test(got.log.length,1);test(got.log[0][0][0],src[0][0]);test(got.log[0][0][1],src[0][1]);
 test(got.log[0].length,src.length);
 test(JSON.stringify(got.log[0].slice(0,16)),JSON.stringify(src.slice(0,16)));
 assert.ok(rounds[idx].url.startsWith('https://tenhou.net/5/#json=%7B%22'));
 assert.ok(!rounds[idx].url.includes('\n'));
 if(rounds[idx].incompleteWin){unknown++;test(got.log[0][16][0],'不明');}
}
const subset=new Set([0,2,rounds.length-1].filter(v=>v<rounds.length));const lines=P.urlsForSelection(rounds,subset,true).split('\n');test(lines.length,subset.size);
for(const line of lines){test(P.parseUrlJSON(line).name.length,4);assert.ok(P.parseUrlJSON(line).name.every(s=>s.endsWith('さん')));}
console.log('PASS: /5/ 인코딩, 국 정보·패 행동 기록 원형 보존, 국 선택, 닉네임 익명화, 화료 결과 보완', {unknown});

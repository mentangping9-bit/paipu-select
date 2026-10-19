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

// Real BigCoach-style settlements: deposits affect winner gains, while honba
// affects payments. Both must be excluded from the base hand description.
function scoringCase(header, outcome) {
 const r=JSON.parse(JSON.stringify(data.log[0]));r[0]=header;r[16]=outcome;
 const v={name:['A','B','C','D'],log:[r]};
 const parsed=P.parseText(JSON.stringify(v))[0];
 return {parsed,end:P.parseUrlJSON(parsed.url).log[0][16]};
}
let c=scoringCase([0,0,0],['和了',[-4000,-2000,10000,-2000],[2,2]]);
test(c.end[2][3],'2000-4000点');test(c.end[2].length,4);test(c.parsed.incompleteWin,false);
assert.ok(c.parsed.scoreSummary.includes('+10,000점'));
assert.ok(c.parsed.scoreSummary.includes('2,000/4,000점'));
c=scoringCase([5,3,4],['和了',[-4200,16600,-4200,-4200],[1,1]]);
test(c.end[2][3],'3900点∀');
c=scoringCase([5,4,0],['和了',[-700,-900,-700,3300],[3,3]]);
test(c.end[2][3],'300-500点');
c=scoringCase([0,2,1],['和了',[5500,-4500,0,0],[0,1]]);
test(c.end[2][3],'3900点');
c=scoringCase([2,0,0],['和了',[-6400,0,0,7400],[3,0]]);
test(c.end[2][3],'6400点');test(JSON.stringify(c.end[1]),'[-6400,0,0,7400]');
const full=['和了',[8000,-8000,0,0],[0,1,0,'満貫8000点','立直(1飜)','ドラ(3飜)']];
test(JSON.stringify(scoringCase([0,0,0],full).end),JSON.stringify(full));
// Do not fabricate scores for missing deltas, liability-like splits, unequal
// dealer tsumo, negative deposits, or ambiguous multi-ron honba allocation.
for(const [header,end] of [
 [[0,0,0],['和了',[],[0,1]]],
 [[0,0,0],['和了',[8000,-4000,-4000,0],[0,1]]],
 [[0,0,0],['和了',[6000,-2000,-1000,-3000],[0,0]]],
 [[0,0,0],['和了',[3000,-4000,0,0],[0,1]]],
 [[0,1,0],['和了',[1300,-1300,0,0],[0,1],[0,-1000,1000,0],[2,1]]]
]) {
 c=scoringCase(header,end);test(c.parsed.incompleteWin,true);test(c.end[0],'不明');
}
console.log('PASS: 실제 정산 타점 복원, 본장·공탁 분리, 원본 역 보존, 불확실한 정산 거부');

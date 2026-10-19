const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../public/link-utils.js'),'utf8');
const context={URL};context.globalThis=context;vm.createContext(context);vm.runInContext(code,context);
const extract=context.MajsoulShare.extract;
const jp='https://game.mahjongsoul.com/?paipu=261014-f0ee926e-6cbc-491b-8f6b-e1e460a2cdfe_a924951866';
const kr='https://mahjongsoul.game.yo-star.com/?paipu=261019-ed6ff58a-5721-4a85-bb86-b7199f7fa668_a917631742';
const en='https://mahjongsoul.game.yo-star.com/kr/?paipu=261014-f0ee926e-6cbc-491b-8f6b-e1e460a2cdfe_a924951866';
for (const value of [jp, `작혼패보 : ${jp}`, `雀魂牌譜：${jp}`, `Mahjong Soul Replay: ${jp}`, `Mahjong Soul\n${jp}\nPlease watch!`, `[패보 링크](${jp})`, `작혼패보: ${jp}.`]) {
  assert.equal(extract(value),jp, 'failed '+value);
}
assert.equal(extract('한국어 안내: '+en), en);
assert.equal(extract('작혼 패보:'+kr),kr);
assert.equal(extract('Mahjong Soul Record: '+kr+'\nshare'),kr);
assert.equal(extract('雀魂牌譜：'+kr),kr);
for (const invalid of ['hello','작혼패보 : https://evil.example/?paipu=261014-f0ee926e-6cbc-491b-8f6b-e1e460a2cdfe', 'https://game.mahjongsoul.com.evil.example/?paipu=261014-f0ee926e-6cbc-491b-8f6b-e1e460a2cdfe']) {
  assert.throws(()=>extract(invalid));
}
console.log('PASS: 한국어/日本語/English/줄바꿈/마크다운/다국적 호스트 공유문구 추출 및 악성 호스트 거절');

/* Mobile-first Mahjong Soul / Tenhou JSON → NAGA per-kyoku converter. No network calls. */
(() => {
  'use strict';
  const EDITOR = 'https://tenhou.net/5/#json=';
  const WINDS = ['동', '남', '서', '북'];
  const JAPANESE_WINDS = ['東', '南', '西', '北'];
  const MAX_BYTES = 10 * 1024 * 1024;
  const isObj = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const validRound = v => Array.isArray(v) && v.length >= 17 && Array.isArray(v[0]) &&
    Number.isInteger(v[0][0]) && v[0][0] >= 0 && v[0][0] < 16 &&
    Array.isArray(v[16]);

  function parseEditorUrl(line) {
    const s = line.trim();
    if (!/^https?:\/\/tenhou\.net\/(?:5|6)\//i.test(s)) return null;
    const hash = s.indexOf('#json=');
    if (hash < 0) throw new Error('천봉 URL에 #json= 데이터가 없습니다. 전적 ID 링크가 아닌 JSON 패보 URL이 필요합니다.');
    const raw = s.slice(hash + 6);
    try { return JSON.parse(raw); }
    catch { return JSON.parse(decodeURIComponent(raw)); }
  }

  function parseText(source) {
    if (typeof source !== 'string') throw new Error('파일을 텍스트로 읽을 수 없습니다.');
    if (source.length > MAX_BYTES) throw new Error('10MB를 넘는 파일은 지원하지 않습니다.');
    const clean = source.replace(/^\uFEFF/, '').trim();
    if (!clean) throw new Error('파일 내용이 비어 있습니다.');
    const fromURL = clean.includes("\n") ? null : parseEditorUrl(clean);
    if (fromURL) return collect(fromURL);
    let input;
    try { input = JSON.parse(clean); }
    catch (e) {
      const lines = clean.split(/\r?\n/).map(v => v.trim()).filter(Boolean);
      if (lines.length > 0 && lines.every(v => /^https?:\/\/tenhou\.net\//.test(v))) {
        return collect(lines.map(parseEditorUrl));
      }
      if (lines.length > 1) {
        try { input = lines.map(v => JSON.parse(v)); }
        catch { throw new Error('JSON이 아니거나 지원하는 천봉 URL 목록이 아닙니다.'); }
      } else {
        throw new Error('JSON 문법을 해석할 수 없습니다: ' + e.message);
      }
    }
    return collect(input);
  }

  function collect(data) {
    // A limited wrapper scan supports JSON exports with data/record/paipu containers.
    const results = [];
    const visited = new Set();
    function walk(v, depth = 0) {
      if (depth > 5 || v == null || typeof v !== 'object' || visited.has(v)) return;
      visited.add(v);
      if (isObj(v) && Array.isArray(v.log) && v.log.every(validRound) && v.log.length > 0) {
        results.push({meta:v, rounds:v.log});
        return;
      }
      if (Array.isArray(v) && v.length && v.every(validRound)) {
        results.push({meta:{}, rounds:v});
        return;
      }
      if (Array.isArray(v)) { v.forEach(item => walk(item, depth + 1)); return; }
      // Explicitly visit probable wrappers only, avoiding scanning analysis blobs.
      for (const key of ['data','result','paipu','record','records','payload','game','games','rounds','hands','items','content','message']) {
        if (Object.hasOwn(v,key)) walk(v[key],depth+1);
      }
    }
    walk(data);
    if (!results.length) throw new Error('표준 천봉/6 패보의 log 배열을 찾지 못했습니다. 빅코치에서 내려받은 실제 JSON 샘플이 있으면 형식에 맞게 확장할 수 있습니다.');
    const all = [];
    for (const entry of results) {
      if (entry.meta.name && (!Array.isArray(entry.meta.name) || entry.meta.name.length !== 4)) {
        throw new Error('NAGA는 4인 마작 패보만 지원합니다.');
      }
      const ruleDisp = String(entry.meta.rule?.disp || '');
      if (/三人|三麻|サンマ/.test(ruleDisp)) throw new Error('NAGA는 3인 마작 패보를 분석하지 못합니다.');
      for (const round of entry.rounds) {
        const no = round[0][0];
        const honba = Number(round[0][1] || 0);
        const label = `${WINDS[Math.floor(no / 4)]}${no % 4 + 1}국`;
        const outcome = round[16]?.[0] || '';
        const meta = entry.meta;
        const repaired = restoreWinScores(round);
        const incompleteWin = isIncompleteWin(repaired.round);
        all.push({ id: all.length, label, honba, result: String(outcome),
          url: buildUrl(meta, repaired.round), roundNo: no, incompleteWin,
          recoveredWin: repaired.recovered,
          scoreSummary: winSummary(repaired.round, meta.name) });
      }
    }
    return all;
  }

  function normalizeName(s) {
    // The Tenhou viewer has trouble with some ASCII special characters.
    return String(s).replace(/[!#<>"%&$*]/g, ch => String.fromCharCode(ch.charCodeAt(0) + 0xFEE0));
  }
  function parseUrlJSON(url) {
    const marker = '#json=';
    const i = url.indexOf(marker);
    if (i < 0) throw new Error('천봉 JSON URL이 아닙니다.');
    const encoded = url.slice(i + marker.length);
    // Both Tenhou's percent-encoded URL and older plain-JSON URLs are accepted.
    try { return JSON.parse(decodeURIComponent(encoded)); }
    catch (_) { return JSON.parse(encoded); }
  }
  function rewriteYaku(round) {
    const r = JSON.parse(JSON.stringify(round));
    const result = r[16];
    // Only genuinely unrecoverable win details use the unknown ending. Short
    // BigCoach details are repaired from their recorded payments before here.
    if (isIncompleteWin(r)) {
      r[16] = ['不明'];
      return r;
    }
    if (!Array.isArray(result) || result[0] !== '和了') return r;
    const prevalent = JAPANESE_WINDS[Math.floor(r[0][0] / 4)];
    const dealer = r[0][0] % 4;
    for (let i = 1; i + 1 < result.length; i += 2) {
      const changes = result[i];
      const details = result[i + 1];
      if (!Array.isArray(details) || !Array.isArray(changes)) continue;
      // The winner is encoded in details[0] by standard tenhou/6 format.
      const winner = Number.isInteger(details[0]) && details[0] >= 0 && details[0] <= 3
        ? details[0] : changes.indexOf(Math.max(...changes));
      const seat = JAPANESE_WINDS[((winner - dealer) + 4) % 4];
      for (let j = 4; j < details.length; j++) {
        if (typeof details[j] !== 'string') continue;
        details[j] = details[j]
          .replace('役牌:場風牌(1飜)', `場風 ${prevalent}(1飜)`)
          .replace('役牌:自風牌(1飜)', `自風 ${seat}(1飜)`)
          .replace('ダブル立直(2飜)', '両立直(2飜)')
          .replace('数え役満', '役満');
      }
    }
    return r;
  }
  function scoreDisplay(kind,a,b,language='ko') {
    const number=n=>n.toLocaleString(language==='ja'?'ja-JP':language==='en'?'en-US':'ko-KR');
    return language==='en'?`${kind==='ron'?'Ron':'Tsumo'} ${number(a)}${b===undefined||b===0?'':'/'+number(b)} points${b===0?' each':''}`:language==='ja'?`${kind==='ron'?'ロン':'ツモ'} ${number(a)}${b===undefined?'':b===0?'':'/'+number(b)}点${b===0?'オール':''}`:kind==='ron'?`론 ${number(a)}점`:b===0?`쯔모 ${number(a)}점씩`:`쯔모 ${number(a)}/${number(b)}점`;
  }
  function paymentScore(round, changes, details, language='ko') {
    const display=(kind,a,b)=>scoreDisplay(kind,a,b,language);
    // The export records settlement payments separately from riichi deposits.
    // Derive points from losers, never the winner's gain (which includes sticks).
    // Do not infer fu, han, yaku, or liability from a payment amount.
    if (!Array.isArray(changes) || changes.length !== 4 ||
        !changes.every(v => Number.isSafeInteger(v) && v % 100 === 0) ||
        !Array.isArray(details) || details.length < 2) return null;
    const [winner, payer] = details;
    if (![winner, payer].every(v => Number.isInteger(v) && v >= 0 && v < 4) || changes[winner] <= 0) return null;
    if (details.length >= 4 && details[2] !== winner) return null;
    const honba = round[0][1], dealer = round[0][0] % 4;
    if (!Number.isInteger(honba) || honba < 0) return null;
    const deposit = changes.reduce((a,b) => a+b, 0);
    if (deposit < 0 || deposit % 1000 !== 0) return null;
    if (winner !== payer) {
      if (changes[payer] >= 0 || changes.some((v,i) => i !== winner && i !== payer && v !== 0)) return null;
      const points = -changes[payer] - honba * 300;
      if (points <= 0 || points % 100 !== 0) return null;
      return {text: `${points}点`, display: display('ron',points)};
    }
    const payers = [0,1,2,3].filter(i => i !== winner);
    if (payers.some(i => changes[i] >= 0)) return null;
    const payments = payers.map(i => -changes[i] - honba * 100);
    if (payments.some(v => v <= 0 || v % 100 !== 0)) return null;
    if (winner === dealer) {
      if (!payments.every(v => v === payments[0])) return null;
      return {text: `${payments[0]}点∀`, display: display('tsumo',payments[0],0)};
    }
    const child = payers.filter(i => i !== dealer).map(i => -changes[i] - honba * 100);
    const parent = -changes[dealer] - honba * 100;
    // Standard rounded nondealer payments differ by at most 100 from 2:1.
    // Nonstandard splits/pao need explicit original detail, not a guess.
    if (child[0] !== child[1] || ![2*child[0], 2*child[0]-100].includes(parent)) return null;
    return {text: `${child[0]}-${parent}点`, display: display('tsumo',child[0],parent)};
  }
  function restoreWinScores(round) {
    const r = JSON.parse(JSON.stringify(round));
    const result = r[16];
    let recovered = false;
    if (result?.[0] !== '和了' || result.length < 3 || result.length % 2 !== 1) return {round:r,recovered};
    // Multiple ron with honba may allocate the honba to only one winner. A
    // shortened result does not say which convention was used.
    if (result.length > 3 && r[0][1] !== 0) return {round:r,recovered};
    for (let i = 2; i < result.length; i += 2) {
      const detail = result[i];
      // Repair only the documented [winner,payer] export. Existing complete
      // score/yaku details and unrecognized variants are never overwritten.
      if (!Array.isArray(detail) || detail.length !== 2) continue;
      const score = paymentScore(r,result[i-1],detail);
      if (!score) continue;
      result[i] = [detail[0],detail[1],detail[0],score.text];
      recovered = true;
    }
    return {round:r,recovered};
  }
  function winSummary(round, names, language='ko') {
    const result = round[16];
    if (result?.[0] !== '和了') return '';
    const parts = [];
    for (let i = 2; i < result.length; i += 2) {
      const detail = result[i], changes = result[i-1];
      if (!Array.isArray(detail) || detail.length < 4 || !Array.isArray(changes)) continue;
      const winner = detail[0];
      // Complete recorded scores take precedence over inferred settlement splits.
      // In a double ron, only one winner may receive the honba payment.
      const recorded=String(detail[3]).match(/(\d+)(?:-(\d+))?点(∀)?$/);
      const display = recorded
        ? scoreDisplay(detail[0]===detail[1]?'tsumo':'ron',Number(recorded[1]),recorded[3]?0:recorded[2]?Number(recorded[2]):undefined,language)
        : language==='en'?String(detail[3]).replaceAll('符',' fu ').replaceAll('飜',' han ').replaceAll('点',' points').replaceAll('∀',' each')
        : language==='ko'?String(detail[3]).replaceAll('点','점').replace('∀','씩'):String(detail[3]);
      const name = Array.isArray(names) ? String(names[winner] || (language==='ko'?`${winner+1}번`:language==='ja'?`${winner+1}番`:`Player ${winner+1}`)) : (language==='ko'?`${winner+1}번`:language==='ja'?`${winner+1}番`:`Player ${winner+1}`);
      const gain = Number.isSafeInteger(changes[winner]) ? (language==='en'?` · gain +${changes[winner].toLocaleString('en-US')} points`:language==='ja'?` · 収入 +${changes[winner].toLocaleString('ja-JP')}点`:` · 수입 +${changes[winner].toLocaleString('ko-KR')}점`) : '';
      parts.push(`${name} ${display}${gain}`);
    }
    return parts.join(' / ');
  }
  function isIncompleteWin(round) {
    const outcome = round[16];
    if (!Array.isArray(outcome) || outcome[0] !== '和了') return false;
    // Tenhou's winner details: winner, payer, liable, score-description, and optional yaku.
    for (let i = 2; i < outcome.length; i += 2) {
      const detail = outcome[i];
      if (!Array.isArray(detail) || detail.length < 4 ||
          !Number.isInteger(detail[0]) || !Number.isInteger(detail[1]) ||
          !Number.isInteger(detail[2]) || typeof detail[3] !== 'string') return true;
    }
    return outcome.length < 3 || outcome.length % 2 !== 1;
  }
  function buildUrl(meta, round) {
    const names = Array.isArray(meta.name) && meta.name.length === 4
      ? meta.name.map(normalizeName) : ['Aさん','Bさん','Cさん','Dさん'];
    const title = Array.isArray(meta.title) ? meta.title : ['四人南喰赤', ''];
    const src = isObj(meta.rule) ? meta.rule : {};
    // Preserve per-suit red-five counts from real converters (aka51/52/53).
    // Replacing these with aka=1 changes red-free games into red-five games.
    const rule = {...src, disp: String(src.disp || '四南喰赤')};
    if (!['aka','aka51','aka52','aka53'].some(key => Object.hasOwn(src,key))) rule.aka=1;
    const data = { title, name: names, rule, log: [rewriteYaku(round)] };
    // Match the user's known-working format literally: /5/#json=%7B%22...
    return EDITOR + encodeURIComponent(JSON.stringify(data));
  }
  function urlsForSelection(rounds, selectedIds, anonymous) {
    const ids = new Set(selectedIds);
    return rounds.filter(r => ids.has(r.id)).map(r => {
      if (!anonymous) return r.url;
      const obj = parseUrlJSON(r.url);
      obj.name = ['Aさん','Bさん','Cさん','Dさん'];
      return EDITOR + encodeURIComponent(JSON.stringify(obj));
    }).join('\n');
  }
  function jsonForSelection(rounds, selectedIds, anonymous) {
    const text = urlsForSelection(rounds, selectedIds, anonymous);
    return text ? text.split('\n').map(parseUrlJSON) : [];
  }
  globalThis.NagaParser = Object.freeze({parseText, urlsForSelection, jsonForSelection, winSummary, isIncompleteWin, parseUrlJSON, collect, MAX_BYTES});
})();

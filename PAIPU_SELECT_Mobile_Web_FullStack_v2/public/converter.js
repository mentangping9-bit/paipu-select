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
        all.push({ id: all.length, label, honba, result: String(outcome),
          url: buildUrl(meta, round), roundNo: no, incompleteWin: isIncompleteWin(round) });
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
    // BigCoach exports many wins with only [winner, payer] and no score/yaku data.
    // Unlike a legitimate Tenhou win result, [2,2] is not a valid scoring detail.
    // Preserve every draw/discard/meld but mark the terminal result unknown,
    // following the user's working tenhou.net/5 sample. Never invent yaku/points.
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
    return outcome.length < 3;
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
  globalThis.NagaParser = Object.freeze({parseText, urlsForSelection, jsonForSelection, isIncompleteWin, parseUrlJSON, collect, MAX_BYTES});
})();

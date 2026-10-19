/* Extract official Mahjong Soul replay URLs from copied share text in any language. */
(() => {
  'use strict';
  const HOSTS = new Set([
    'game.mahjongsoul.com',
    'mahjongsoul.game.yo-star.com',
    'mahjongsoul.com',
    'www.mahjongsoul.com',
    'game.maj-soul.com',
    'game.maj-soul.net'
  ]);
  const ID = /^[A-Za-z0-9_-]{20,160}$/;
  const URLS = /https:\/\/[^\s\u00a0<>"'`]+/gi;
  const TRAILING = /[)\]}>.,!?;:。．，、！？）」』】]+$/gu;

  function extract(text) {
    if (typeof text !== 'string' || text.length > 8192) {
      throw new Error('작혼 공유 문구가 너무 길거나 올바르지 않습니다.');
    }
    const candidates = text.replace(/&amp;/gi, '&').match(URLS) || [];
    for (const candidate of candidates) {
      const stripped = candidate.replace(TRAILING, '');
      let url;
      try { url = new URL(stripped); } catch { continue; }
      if (url.protocol !== 'https:' || !HOSTS.has(url.hostname.toLowerCase()) ||
          url.port || url.username || url.password) continue;
      const ids = url.searchParams.getAll('paipu');
      if (ids.length !== 1 || !ID.test(ids[0])) continue;
      return `${url.origin}${url.pathname || '/'}?paipu=${encodeURIComponent(ids[0])}`;
    }
    throw new Error('복사한 내용에서 공식 작혼 패보 링크를 찾지 못했습니다. 공유 문구 전체를 붙여넣어도 됩니다.');
  }
  globalThis.MajsoulShare = Object.freeze({extract});
})();

/* Copy URL lists as text, without URL sanitizers changing %, case or newlines. */
(() => {
  'use strict';

  function htmlForText(text) {
    const escaped = text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
    return '<pre>' + escaped + '</pre>';
  }

  function isIOS() {
    const navigator = globalThis.navigator || {};
    return /iP(?:hone|ad|od)/.test(navigator.userAgent || '') ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }

  function copySelection(text, textarea, html) {
    if (!textarea) return false;
    const document = textarea.ownerDocument;
    let suppliedText = false;
    const onCopy = event => {
      if (!event.clipboardData) return;
      event.clipboardData.setData('text/html', html);
      event.clipboardData.setData('text/plain', text);
      event.preventDefault();
      suppliedText = true;
    };
    document.addEventListener('copy', onCopy, true);
    try {
      textarea.focus({preventScroll: true});
      textarea.select();
      textarea.setSelectionRange(0, text.length);
      return Boolean(document.execCommand('copy') && suppliedText);
    } catch (_) {
      return false;
    } finally {
      document.removeEventListener('copy', onCopy, true);
    }
  }

  async function copyText(text, textarea) {
    if (typeof text !== 'string' || !text.trim()) return false;
    const html = htmlForText(text);
    const navigator = globalThis.navigator || {};
    const ios = isIOS();
    // On iOS, run the copy event while the tap is active, BEFORE async APIs.
    // WebKit's plain-text write path can also advertise NSURL, and iOS pasting
    // into a textarea may prefer that URL over the original multiline text.
    // Explicit copy-event formats use a separate native registration path.
    if (ios && copySelection(text, textarea, html)) return true;
    const clipboard = navigator.clipboard;
    if (clipboard?.write && typeof globalThis.ClipboardItem === 'function') {
      // HTML first preserves line boundaries in consumers preferring rich text;
      // both representations contain exactly the same URLs, with no anchors.
      for (const formats of [
        {'text/html': new Blob([html], {type: 'text/html'}), 'text/plain': new Blob([text], {type: 'text/plain'})},
        {'text/plain': new Blob([text], {type: 'text/plain'})}
      ]) {
        try { await clipboard.write([new ClipboardItem(formats)]); return true; }
        catch (_) { /* Try the next supported representation. */ }
      }
    }
    if (clipboard?.writeText) {
      try { await clipboard.writeText(text); return true; }
      catch (_) { /* Leave the output available for manual selection. */ }
    }
    return ios ? false : copySelection(text, textarea, html);
  }

  function inspectPaste(expected, actual) {
    const normalize = value => value.replace(/\r\n?/g, '\n').trim();
    const original = normalize(expected), pasted = normalize(actual);
    const expectedLines = original ? original.split('\n').length : 0;
    const actualLines = pasted ? pasted.split('\n').length : 0;
    let state = 'changed';
    if (!pasted) state = 'empty';
    else if (pasted === original) state = 'match';
    else if (expectedLines > actualLines && pasted.replaceAll('\n', '') === original.replaceAll('\n', '')) state = 'linebreaks';
    return {state, expectedLines, actualLines};
  }

  globalThis.PaipuClipboard = Object.freeze({copyText, inspectPaste, isIOS});
})();

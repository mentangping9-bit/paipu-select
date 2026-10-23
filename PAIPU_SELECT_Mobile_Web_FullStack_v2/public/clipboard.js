/* Copy URL lists as text, without URL sanitizers changing %, case or newlines. */
(() => {
  'use strict';

  async function copyText(text, textarea) {
    if (typeof text !== 'string' || !text.trim()) return false;
    const clipboard = globalThis.navigator?.clipboard;
    // An explicit text/plain Blob avoids the URL-specific writeText path used
    // by some browsers. Never write text/uri-list or alter the generated URLs.
    if (clipboard?.write && typeof globalThis.ClipboardItem === 'function') {
      try {
        const item = new ClipboardItem({
          'text/plain': new Blob([text], {type: 'text/plain'})
        });
        await clipboard.write([item]);
        return true;
      } catch (_) { /* Older browsers may only support writeText. */ }
    }
    if (clipboard?.writeText) {
      try {
        await clipboard.writeText(text);
        return true;
      } catch (_) { /* Keep the manual selection available below. */ }
    }
    if (!textarea) return false;
    const document = textarea.ownerDocument;
    let suppliedText = false;
    const onCopy = event => {
      if (!event.clipboardData) return;
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

  globalThis.PaipuClipboard = Object.freeze({copyText});
})();

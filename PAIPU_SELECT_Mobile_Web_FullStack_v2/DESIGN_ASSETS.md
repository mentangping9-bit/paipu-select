# Subculture theme assets

- `public/assets/mascot.webp`: original generated chibi mascot based on the
  user-approved PAIPU SELECT UI concept. Transparent, 720×480, about 60 KB.
  No speech bubbles, slogans, or promotional phrases are embedded in the image.
- `public/assets/wordmark.svg`: custom two-line vector wordmark traced from the
  user-provided original PAIPU SELECT concept. It preserves the uneven lettering,
  dotted i, check tile and mahjong tile in SELECT, with clean floral accents.
  The background is transparent; the artwork contains only SVG paths/circles,
  with no font, embedded bitmap, remote resource or runtime image service.
- `public/assets/Nunito-OFL.txt`: Nunito's SIL Open Font License, distributed with
  the English UI font. Font source: https://github.com/google/fonts/tree/main/ofl/nunito

All assets are served locally on both the static frontend and original backend.
The production static build copies the public assets directory; the Python
server permits only explicitly named asset paths, with its existing file boundary
and response security headers.


## Rounded description fonts

Explanatory copy uses local WOFF2 subsets of NanumSquareRound Regular (Korean), Zen Maru Gothic Medium
(Japanese), and Nunito SemiBold (English). Fonts use `font-display: swap`; dynamic
characters outside the UI subset fall back to the system font. No runtime font
CDN request is made. Form values, replay scores and headings retain their prior
fonts. Derived font families use distinct Paipu names; the Korean subset is named
Paipu Soft Round Korean to respect the upstream Reserved Font Names.

Upstreams (SIL Open Font License; license files in `public/assets`):
- https://hangeul.naver.com/font (NanumSquareRound Regular, `NanumSquareRoundR.ttf`)
- https://github.com/google/fonts/tree/main/ofl/zenmarugothic (`ZenMaruGothic-Medium.ttf`)
- https://github.com/google/fonts/tree/main/ofl/nunito (`Nunito[wght].ttf`, save as `nunito.ttf`)

Regenerate after adding UI copy: install `fonttools[woff]`, place upstream TTFs
in a source directory, then run `python scripts/build-ui-fonts.py SOURCE_DIR`.
The subset includes characters from public JavaScript and HTML, ASCII and common
UI punctuation. Static and Python CSPs allow fonts only from their own origin.
The inline globe is a code-native SVG decoration within the language select label.

Nanum font license notice: https://help.naver.com/service/30016/contents/18088?osType=PC&lang=ko
The original copyright, Reserved Font Name notice and full OFL text accompany
the subset in `public/assets/NanumSquareRound-LICENSE.txt`.

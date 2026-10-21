# Subculture theme assets

- `public/assets/mascot.webp`: original generated chibi mascot based on the
  user-approved PAIPU SELECT UI concept. Transparent, 720×480, about 60 KB.
  No speech bubbles, slogans, or promotional phrases are embedded in the image.
- `public/assets/wordmark.svg`: custom two-line wordmark using outlined Nunito
  Black letterforms with a small check tile and flower. No remote fonts or image
  services are needed at runtime.
- `public/assets/Nunito-OFL.txt`: Nunito's SIL Open Font License, distributed with
  the outlined wordmark. Font source: https://github.com/google/fonts/tree/main/ofl/nunito

All assets are served locally on both the static frontend and original backend.
The production static build copies the public assets directory; the Python
server permits only the three named asset paths, with its existing file boundary
and response security headers.

# Free static frontend

Public entry: https://paipu-select-web.onrender.com
Backend and operator setup: https://paipu-select.onrender.com/?setup=1

The static site publishes only the seven allowlisted frontend assets plus its
public backend-origin configuration. It never contains environment variables,
credentials, Python sources, SQL, fixtures, or uploaded records.

`node PAIPU_SELECT_Mobile_Web_FullStack_v2/build-static.js` builds from the repo
root into `PAIPU_SELECT_Mobile_Web_FullStack_v2/static-dist`. Both services deploy
main automatically. The static service has no paid instance or persistent disk.
Normal Render workspace bandwidth/build allowances still apply.

The page and local JSON conversion work independently of backend availability.
One health-check sequence starts on page load, stops on success or after two
minutes, and does not call Mahjong Soul. Conversion waits for readiness before
submitting exactly once. An old open page checks readiness again after a minute
when conversion is requested. There is no scheduled traffic or keepalive.

The backend allows only the exact static origin and four public API paths.
Operator mutations remain same-origin and operator-key protected. Cross-origin
conversion uses no cookies or credentials. A signed random anonymous visitor
identifier travels in X-Paipu-Visitor for queue ownership; this is not a game
account token, grants no operator access, and is kept only in page memory.
Existing FIFO, per-visitor limits, aggregate rate limits and account cooldowns
are unchanged. Other origins, forged visitor signatures, and cross-origin
operator preflights are covered by HTTP tests.

The original backend URL still has Render's cold-start behavior. First-page
instant loading requires using the new static entry URL. Actual link conversion
can still wait for the free backend to start. Operator setup stays on the backend.

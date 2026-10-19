# Authentication investigation — 2026-10-19

Status: implementation corrections and offline regressions verified; live game
login and the two supplied Korean/JP replay downloads are still unverified.
Code 110 has not yet been demonstrated to be resolved.

## Observed deployment

- Render service srv-dbasu1e7bikc73arl3og, main branch.
- Root: PAIPU_SELECT_Mobile_Web_FullStack_v2.
- /api/health returned version 2.7 at investigation start.
- Deployed commit: 3c5f1abc135d496f7764b193580d87227510cf31.
- v2.8 was uploaded into nested directories that the service did not execute.

## Function-level comparison

Compared with Soulless commit 933a9dd34b8041123007c5b9be70bd95826e70cf
(v0.3.2) and its soulless_proto 0.11.612 metadata.

| Stage | Previous executing code | Current implementation | Reference |
|---|---|---|---|
| SDK send-code | Account, Randstr, Ticket | Account | Auth.Yostar.request_email_code |
| SDK user/login | CheckAccount/Geetest/UserName | Type/OpenID/Token/Secret/CheckAccountPlus | Auth.Yostar.login |
| SDK saved device | quick-login | quick-login; immediately persist rotated token even on later failure | Auth.Yostar.login_with_saved_session |
| WS endpoint | host/gateway | host root for international servers | Endpoint.lobby_socket |
| Route query | productVersion read from HTML | separately named product version | Route.resolve_id |
| requestConnection | type/route/time/platform | type=1, discovered route, time, platform=Web, bounded response wait | Implementation.Lobby.request_connection |
| OAuth auth/check/login | JP=21, EN/KR=22 | Yostar session=22 for every international region | Implementation.Lobby.login_type_for_login_method |
| client_version_string | WebGL_2022-4.0.x | WebGL_2022-0.16.229 | Util.client_version_string; soulless_proto metadata |
| client_version | resource=4.0.x, package missing | resource=0.16.229; package=4.0.12 KR/JP, 4.0.10 EN | Util.client_version_info |
| login tag/reconnect | majsoul-hk-client / true | account region / false | Implementation.Lobby.oauth2_login |

These are concrete deviations from the reference protocol, not proof that any
single deviation caused the observed 110. A successful SDK login is not a
successful game login. A successful game login is not a successful replay fetch.

Live HTTP checks: international route API returned official en-1/en-2 routes.
Official JP and EN web HTML product versions matched the recorded 4.0.12 and
4.0.10 versions. Resource-version mapping comes from soulless_proto, not HTML.
Local outbound WebSocket handshake timed out; deployment checks are needed.

## Reproducible checks

Run from repository root:

    python -m pytest PAIPU_SELECT_Mobile_Web_FullStack_v2/tests -q
    node PAIPU_SELECT_Mobile_Web_FullStack_v2/tests/check.js
    node PAIPU_SELECT_Mobile_Web_FullStack_v2/tests/check-share.js

Tests use a local HTTP SDK stub and mocked game RPC responses. They test HTTP
signatures, token separation/rotation, public wire capture, login field contracts,
request rejection, cookies, selection and unchanged tile actions. They do not
contact a real account and must not be reported as live authentication success.

The startup gateway probe only establishes requestConnection. Its health result
explicitly sets authenticated=false. It does not send account credentials.

## NAGA boundary

Official custom analysis supports Tenhou editor JSON and one-round records.
https://naga.dmv.nico/naga_report/top/
The order form redirects to login without an authenticated NAGA account.
https://naga.dmv.nico/naga_report/order_form/

PAIPU SELECT copies one URL per selected round and opens the official form.
It does not read NAGA cookies or call custom_haihu_analyze, which charges NP.
There is no verified public cross-origin prefill interface; the user pastes the
copied URLs in NAGA and confirms the final order there. Actual acceptance of
percent-encoded /5/ URLs and incomplete ['不明'] endings still requires a logged-in
form validation check. Generated URLs alone are not evidence of NAGA acceptance.

## Sources

- https://git.honk.li/czen/soulless (protocol comparison only; no implementation copied)
- https://hex.pm/packages/soulless_proto/0.11.612 (version metadata)
- https://github.com/Longhorn-Riichi/InjusticeJudge/issues/37 (public requestConnection capture)
- https://github.com/LekangZou/Mahjong-Replay-Converter (MIT helper subset bundled with license)

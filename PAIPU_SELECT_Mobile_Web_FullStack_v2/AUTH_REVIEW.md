# Authentication investigation — 2026-10-19

Status: actual KR account game login and retrieval of the supplied Korean replay
succeeded on 2026-10-19. The server auth status showed authenticated=true,
game_authenticated=true, region=kr. The first conversion response was rejected
by the old list-only validator, because tensoul emits tuple round headers and
result records. JSON-array normalization and a real converter-output regression
were added. Final full-path replay response and NAGA acceptance remain pending.
The first live-account test reached oauth_auth and returned code 151 with resource
version 0.16.229. A credential-free A/B control reproduced 151 with 0.16.229
and returned the expected invalid-credential code 110 with 0.16.266.
The subsequent live KR account authentication succeeded using type 23 and the
resolved 0.16.266 resource version. Thus the authentication correction is now
account-verified, independently of final conversion-response validation.

## Observed deployment

- Render service srv-dbasu1e7bikc73arl3og, main branch.
- Root: PAIPU_SELECT_Mobile_Web_FullStack_v2.
- /api/health returned version 2.7 at investigation start.
- Deployed commit: 3c5f1abc135d496f7764b193580d87227510cf31.
- v2.8 was uploaded into nested directories that the service did not execute.

## Function-level comparison

Initial comparison used Soulless commit 933a9dd34b8041123007c5b9be70bd95826e70cf
(v0.3.2) and its soulless_proto 0.11.612 metadata. These contain a stale
resource version and an EN-only OAuth type hardcode. The final implementation
is grounded in the actual game client dump czen/mjs_src commit
b29f2ed950d51e428b7b884ee2dbc2e8501ecaa3 (2026-10-12), especially
GameUtility.ELoginSocialType, Basic.Enum, YostarWebGLSDK.Login and
UI_Entrance.LoginBySocioCode, plus live official resource assets.

| Stage | Previous executing code | Current implementation | Reference |
|---|---|---|---|
| SDK send-code | Account, Randstr, Ticket | Account | Auth.Yostar.request_email_code |
| SDK user/login | CheckAccount/Geetest/UserName | Type/OpenID/Token/Secret/CheckAccountPlus | Auth.Yostar.login |
| SDK saved device | quick-login | quick-login; immediately persist rotated token even on later failure | Auth.Yostar.login_with_saved_session |
| WS endpoint | host/gateway | host root for international servers | Endpoint.lobby_socket |
| Route query | productVersion read from HTML | separately named product version | Route.resolve_id |
| requestConnection | type/route/time/platform | type=1, discovered route, time, platform=Web, bounded response wait | Implementation.Lobby.request_connection |
| OAuth auth/check/login | JP=21, EN/KR=22 | KR=23, JP=21, EN=22 | Actual client ELoginSocialType + SDK selection |
| client_version_string | WebGL_2022-4.0.x | WebGL_2022-<live resource version> | GameUtility.GetClientVersionString; official resource version asset |
| client_version | resource=4.0.x, package missing | resource=live KR 0.16.266 / JP 0.16.267; separate package | Util.client_version_info |
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

## Live version evidence and update behavior

The official HTML identifies the Unity data file. Its GameLoader MonoBehaviour
contains the clientbundlesettings URL. That JSON names warehouseSettings, whose
bundlePath names the WebGL/ASTC resource distribution. The live manifest maps
MyAssets/docs_version/version.json to a small bundle containing the version.

KR: product 4.0.12, resource 0.16.266, live hash
28968f9ea893df2a59c555e9fed9b7662f412d37.
JP: product 4.0.12, resource 0.16.267, live hash
9d063fe26e9ea592263da855da5342f3155e1c43.
These were read directly from the official distribution on 2026-10-19.

version_resolver.py checks the official distribution before authentication and
caches it for five minutes. An unchanged verified hash can use the recorded
version. A changed hash triggers extraction of the new version asset. A changed
product build triggers re-extraction of its GameLoader settings URL. Only fixed
official hosts are allowed; user replay URLs cannot direct these requests.

Actual production UI actions confirmed east/south/all/none selection, distinct
honba labels, zero-selection disabling and one-round-per-URL headers using an
anonymous test fixture. Cloud Browser's virtual clipboard cannot read the
page clipboard, and its available APIs do not expose mobile viewport emulation.
Clipboard delivery, NAGA acceptance and mobile rendering remain unverified.

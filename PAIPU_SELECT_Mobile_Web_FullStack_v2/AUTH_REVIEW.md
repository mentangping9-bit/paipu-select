# Authentication investigation — 2026-10-19

## Confirmed account recovery — 2026-10-25, v3.10.2

Clears historical account priority/refill penalties on a real successful
post-rest fetch, preserves quota history and global holds, and permits a
bounded real recovery opportunity when a hold expires. Existing verified
comebacks are reconciled using persisted last_success_at after last_error,
with no active restriction and no new provider calls. Tests cover exactly the
five requested historical accounts, unchanged credentials/counters/history,
idempotent restart, and refusal to normalize active/unconfirmed restrictions.

## Load-aware admission — 2026-10-24, v3.10.0

Added a bounded credential-free scheduler under encrypted usage.load_scheduler.
The production pool explicitly enables it for synchronous, queued and private
validation fetches. All claims/outcomes reuse the token row advisory lock; slot
auth refresh/re-enrollment preserves usage. The actual provider quotas remain
unknown. Conservative starting rates and recovery thresholds are documented in
README; no extra game probes or keep-alive jobs were added. Existing 17/20 and
five-hour holds, cache-first reads, operator authorization and FIFO switch remain.
Tests use real encryption and simulated SQL/game responses to exercise cross-
process claims, 20-slot rotation, shrinking capacity, rolling caps, cooldowns,
re-enrollment, slow recovery, safe queue waiting and bounded ciphertext size.
Live 540 incidence reduction requires observation after deployment; it cannot be
established by mocked tests or by provoking production rate-limit failures.

## Retrieval protection — 2026-10-23, v3.9.0

Final operator policy: 3 upstream starts per rolling minute, at least 20 seconds
apart; five-hour holds per account for replay-stage 540 only; five-hour global
pause when **17 accounts currently have active 540 holds**. This replaces the
proposed consecutive-error trigger, which was not deployed. The global deadline
is fixed once opened; re-enrollment, polling, cached results and restarts do not
shorten or extend it. Admission and holds use the existing encrypted vault.

Tests exercise the 16/17 boundary with twenty synthetic encrypted accounts,
restart and re-enrollment preservation, excluded expired/non-540 holds, legacy
failure-time upgrade, 20-second spacing and rolling admission, pending-ticket
termination, and HTTP 503 localized notice while cached conversions still return
HTTP 200 without any provider calls. Real provider limits are never intentionally
triggered to validate this behavior. Existing OAuth fields are unchanged.

## Retrieval architecture update — 2026-10-23, v3.8.0

Compared Amae Koromo scripts at d375252fefd2bb6b1cca82b409b7a1abcf155197
(`majsoul.js`, `logGames.js`) with this service. Amae keeps a connection for a
finite retrieval batch and persists replay data; its statistical UI mostly reads
stored data. PAIPU previously refreshed the SDK and opened/authenticated/closed
a socket for each cache miss, with only a 15-minute in-memory replay cache.
The current KR/JP/EN OAuth fields are preserved; the change adopts connection
and data reuse rather than copying legacy regional authentication fields.

The public `Equim-chan/mjai-reviewer` source inspected at
2dc5ec5c8b28517cfb45f57eb21536d9a8f67aa9 does not publish the complete current
Mortal site's Mahjong Soul retrieval backend. Its Tenhou downloader and old
Mahjong Soul documentation cannot prove that the current service is immune to
540. No official quota or account-unblocking claim follows from this comparison.

Local tests exercise two fetches over one real local WebSocket using actual
protobuf RPCs and the converter, SDK freshness expiry, token-change/logout/error
connection invalidation, idle closure, encrypted cache restoration, a shared
10/min window across independent instances, and a persisted 540 pause. These
provider stubs do not establish live account success. The additive cache-table
migration was tested on a Neon branch with the restricted runtime role and
forced RLS, then applied to production without changing the auth-row ciphertext
length or updated_at. See deployment logs/final verification for live results.

Live v3.8.0 validation on Render, 2026-10-23 13:43 UTC: eligible slot 20
retrieved the supplied Korean replay (10 rounds) and Japanese replay (14 rounds).
The bounded probe logged `complete opened 1 reused 1`. Real-driver test-branch
checks passed TLS, restricted role, encryption roundtrip, independent connection
restore, wrong-key rejection and forced RLS. The two production cache entries
contained 8,688 ciphertext bytes. After clearing the verification settings and
redeploying, the Korean replay was restored in the UI without changing the game
connection counters. Separate visitor requests still returned replay-stage 540
on slots 2 and 3, so the update is not an unblock or proof of quota removal.

That restart test also exposed a busy-response path for a stored Japanese replay:
durable hits were checked after the upstream pending-capacity guard. v3.8.1 moves
encrypted cache reads ahead of that guard and uses independent read-only queries
without the authentication advisory lock. A regression test holds every upstream
slot and the auth lock simultaneously and verifies a durable hit still returns.

Status: actual KR account game login and retrieval of the supplied Korean replay
succeeded on 2026-10-19. The server auth status showed authenticated=true,
game_authenticated=true, region=kr. The first conversion response was rejected
by the old list-only validator, because tensoul emits tuple round headers and
result records. JSON-array normalization and a real converter-output regression
were added. The deployed fix subsequently retrieved and converted both supplied
replays (10 and 11 rounds respectively). NAGA server-side acceptance remains
unverified; its official public client validation passed for the tested outputs.
The first live-account test reached oauth_auth and returned code 151 with resource
version 0.16.229. A credential-free A/B control reproduced 151 with 0.16.229
and returned the expected invalid-credential code 110 with 0.16.266.
The subsequent live KR account authentication succeeded using type 23 and the
resolved 0.16.266 resource version. Thus the authentication correction is now
account-verified, independently of final conversion-response validation.

## Initial deployment

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
4.0.10 versions. The final resource-version resolver reads official live assets rather than
trusting the stale soulless_proto metadata or the HTML product version. Local
outbound WebSocket handshake timed out; production authentication and replay
retrieval subsequently succeeded on Render.

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
copied URLs in NAGA and confirms the final order there.

The official publicly served scripts were retrieved on 2026-10-19:
- https://naga.dmv.nico/static/js/order_form.js (custom_haihu_order/check_url)
- https://naga.dmv.nico/static/js/tenhou_edit.js (TenhouEdit/check)

Their original URL and tile-sequence validation code was run locally against
anonymized URLs generated by the production UI, without calling the order API:
- KR sample: selected East 1 honba 1 and South 4 honba 2; both passed.
- Second supplied game.mahjongsoul.com sample: all 11 independent round records
  passed, including the nine-terminals abortive draw.
- Each record had exactly one log. The first URL checker accepted the actual
  percent-encoded /5/#json= format. The batch limit in the official checker is
  30 rounds; larger custom batches must be split before NAGA submission.

These checks validate NAGA's client-side input rules, not authenticated server
acceptance. Niconico's account domain is blocked by the Cloud Browser's site
safety policy, so the authenticated form could not be reached. No NP was spent.
The tested winning records contain actual score/yaku details. Compatibility of
incomplete ['不明'] winning records has not been established by a real replay.

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

## Final production verification

Executable commit: 20e27b8f35a5852f8abce2500d3f77ce5d8cff3b.
Render deploy: dep-dbb20th42hec73e5m3h0, live on 2026-10-19.
The root compatibility entry point runs the canonical application folder.
Health returned version 3.0.0-dev, this executable commit, and resource 0.16.266.

Actual production UI actions on the supplied Korean replay confirmed:
- 10 rounds fetched from the game server and converted, with distinct honba.
- East/South selections each selected five rounds; all/none selected 10/0.
- Only East 1 honba 1 and South 4 honba 2 were exported, with headers
  [0,1,1] and [7,2,0], one log per record, and preserved red-five rules.
- The actual JSON download contained those two records (7715 bytes).
- The second supplied replay was fetched using the same KR account session,
  despite the different share-link host, and produced 11 rounds.

Local regression suite: 16 passed plus 15 subtests; both Node checks passed.
These tests complement the live evidence; they are not substitutes for it.
Cloud Browser's virtual clipboard cannot read navigator.clipboard writes, and
its available APIs do not expose mobile viewport emulation. Clipboard delivery
to NAGA, authenticated server acceptance and mobile-device rendering remain
unverified. The deployed UI provides manual URL selection and TXT/JSON download
fallbacks and never initiates a paid order automatically.

## Short JSON win-score restoration — 2026-10-19

BigCoach exports may retain complete payment deltas but abbreviate winner detail
to [winner,payer]. Previously those wins were replaced by ["不明"]. The browser
now retains the original payment vectors and creates a score-only detail from
losers' payments, subtracting 300 per honba for ron or 100 per payer for tsumo.
Winner gains include deposits and are displayed separately from base payments.
No fu, han or yaku are inferred. Complete original details remain intact.

Ambiguous splits (including possible liability), missing deltas and ambiguous
multi-ron honba allocation remain unresolved rather than gaining invented data.
A previously exported ["不明"] record has already lost its winner and payment
metadata and cannot be repaired; the original JSON must be imported again.

The user-supplied 12-round JSON was reproduced in production before the patch:
all nine wins were shortened. Local patched conversion recovered all nine win
scores and retained all three draws and all tile actions/payment deltas. The
official NAGA public URL and TenhouEdit validators passed all twelve outputs.
The private upload is not committed to this public repository. Tests use generic
settlement examples to cover deposits, honba, original detail preservation and
ambiguous payment rejection. Authenticated NAGA server acceptance is still not
claimed by these client-side checks.


## JP SDK project correction (2026-10-20, 3.3.3)

The older Soulless JP identifier JP-MAJONGSOUL is not accepted by the
current JP SDK. Its PROJECT_NOT_EXIST constant is 300200 in the client
YoStar.SDK.ResultCode. Mahjong-Replay-Converter uses JP-MJ/ja, and the
extracted game UI_Entrance migration URL also identifies pid=JP-MJ.
A bounded live diagnostic sent empty Account/Code to get-auth, without
sending mail or submitting any user's OTP: JP-MAJONGSOUL returned 300200;
JP-MJ returned CLIENT_PARAMETER_ERROR (100400), as expected for empty fields.
This verifies recognition of the project, not a successful account login.
Use JP-MJ/ja only for JP; preserve the working KR and EN issuer mappings.
Return a server configuration error for 300200 instead of blaming an OTP.
Full JP OTP exchange and game retrieval still need live completion.

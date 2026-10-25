# PAIPU SELECT application

## v3.10.2 · normal treatment after confirmed recovery

One real successful retrieval after a 540 rest now clears the account's local
slowdown/probation immediately. The historical error, last attempt and rolling
usage remain. Unconfirmed recovery retains a single trial credit after its hold
expires, but account selection no longer places every penalized account behind
all healthy accounts; it compares current utilization and oldest attempt. No
synthetic recovery probes or requests to consume unused past allocations.
Previously successful comebacks are normalized on startup (and reconciled on
request) from their persisted post-error success, without querying Mahjong Soul.
Active holds, re-enrollment without retrieval and successes older than the latest
540 cannot clear a penalty. Global adaptive slowdown and five-hour protections
remain unchanged. The 20-account baseline returns to one new retrieval per
minute when all accounts are normal and no global slowdown applies.

## v3.10.1 · selected account check

Optional private `PAIPU_SELECTED_CHECK_ID`, `PAIPU_SELECTED_CHECK_URL` and
`PAIPU_SELECTED_CHECK_SLOTS` run one requested replay query per selected account
(up to five). Claims are persisted atomically with account-budget reservations,
so the same revision never replays a slot after restart. At most eight bounded
run records are retained; filling this bound fails closed. The check respects
account holds, local budgets, shared pacing and the 17-account global stop. It
waits only for admission without issuing provider probes; actual provider errors
are never retried. It has a 30-minute maximum duration and no public trigger.
Clear the three non-secret configuration values after the requested check.
Normal account selection and all existing protection settings are unchanged.

## v3.10.0 · load-aware account scheduling

The production pool prefers lower-penalty accounts, then remaining credit and
short/long-window utilization, with oldest attempt as the tie-break, instead of
blindly advancing the slot. Recovery accounts are not preferred over healthy
accounts merely because they rested longer.
These are **conservative application settings, not verified provider quotas**:

- Minimum 400 seconds per account; at most 2 attempts per rolling 10 minutes
  and 18 per rolling 6 hours. Failure attempts consume the same budget.
- A normal account refills one local credit per 1,200 seconds, stores at most
  three and starts migration with one. With 20 fully usable accounts, the whole
  service starts at about one new retrieval per minute (the outer 3/min cap is
  retained). Fewer usable accounts or penalties reduce this throughput.
- Replay-stage 540 retains the five-hour hold and doubles that account's refill
  interval, up to 8x. It returns with one trial credit; a successful trial
  discards accumulated holiday credits and preserves the refill penalty.
- Two distinct accounts reporting 540 within 10 minutes double the shared
  scheduling interval (up to 8x). Events used for a slowdown are consumed, so
  the same pair cannot repeatedly trigger a slowdown. A non-replay/auth error
  does not count toward this signal.
- Recovery never follows idle time alone: one penalty level is removed only
  after at least six hours without 540 and 10 actual successes for an account,
  or 60 actual successes for the global scheduler. These operational thresholds
  do not constitute a statistical guarantee of safe provider capacity.
- The existing 17-account / five-hour global stop remains unchanged. A 540 is
  returned once; even when FIFO is enabled, the failed replay is not cascaded
  automatically through backup accounts. FIFO's production switch is unchanged.
- Bounded histories, credits, penalties and starts are encrypted in the existing
  usage row and claimed under the existing cross-process advisory lock before
  I/O. Re-enrollment and redeploys do not reset them. No new tables or services.
- Operator-only statistics show window counts, credit refill interval, probation
  and protection wait. Public local-budget waits use ACCOUNT_LOAD_LIMITED and
  do not disable cached replay retrieval or local JSON conversion.

## v3.9.1 · public pause notice

The homepage shows the existing mascot with one tear in the usage notice. During a persisted global retrieval pause, a prominent card shows a local HH:MM:SS countdown. Anonymous `/api/service/status` exposes only `paused` and `retry_after`, with shared reads cached for 15 seconds; it never calls Mahjong Soul. Visible tabs refresh this status at most once per minute and when the countdown expires. Hidden tabs stop status polling. Cache retrieval and local JSON conversion remain available. A failed status read does not announce a reopening. The previous FIFO queue configuration is unchanged.

## v3.9.0 · conservative retrieval policy

Production requests are admitted at most three per rolling minute, with at least
20 seconds between starts across deployments. Each replay-stage 540 places only
that account in a five-hour hold. Its explicit `rate_limit_until` is separate from
network/SDK cooldowns. Successful accounts and non-540 pauses are not counted.
Legacy unrecovered 540 holds are upgraded from their recorded failure time,
never from server startup; re-enrollment preserves the hold.

When **17 of the 20 accounts are simultaneously in active 540 holds**, new replay
retrievals pause for five hours from detection. This is a count of current holds,
not consecutive errors or a 30-minute error window. The encrypted admission
state survives redeployments. Polling, account re-enrollment, falling below 17
and unrelated successful requests cannot shorten or extend an active global
pause. Requests become eligible again after it expires, subject to account holds.

Cached replays remain available through both synchronous and queued endpoints.
During a global pause, new uncached requests return HTTP 503 `SERVER_CONGESTED`,
`Retry-After`, `retry_after`, and `retry_at`, with a polite localized explanation.
Pending tickets terminate with the same message instead of polling for hours.
The notice doesn't disable cached-replay input or JSON upload. Operator status
includes the current protected-pause state and active 540 account count.

The FIFO queue, when enabled, is capped at 30 pending/running jobs and a
ten-minute maximum wait. Duplicate replay requests are coalesced. A 540 waits
at least 60 seconds before any queued retry, with at most three 540 responses per
job; the 17-account global pause terminates retries. Neither polling nor waiting
calls the provider. The queue remains in memory; a restart expires old tickets.
No artificial provider failures or additional verification emails are needed to
test these safeguards. Local tests use synthetic encrypted account records.
`PAIPU_REPLAY_QUEUE_ENABLED` remains the operator's activation switch. Its previous
production value was false; changing it to true needs explicit operator approval.
All account/global holds and the 3/min limit also apply in synchronous mode.

## v3.8.1 · request-driven connection reuse and durable replay cache

The existing KR/JP/EN OAuth wire fields are unchanged. Requests run on one lazy
game event loop. An authenticated socket can serve subsequent requests for the
same account/token; logout, token/version changes and errors close it. Idle
sockets close after five minutes; connections older than fifteen minutes are
replaced on demand. No periodic game RPCs, pings or keep-alive jobs are added.
SDK refresh results are reused for five minutes from the actual refresh time.

Run `sql/replay_cache.sql` as the owner on an isolated test branch first, then on
the existing database. Fresh installations require both `sql/session_vault.sql`
and `sql/replay_cache.sql`. The existing restricted runtime role gains CRUD only
on the separate replay-cache table, with forced RLS. Authentication-table rights
are unchanged. Cache keys are SHA-256 hashes and compressed replay JSON is
Fernet-encrypted with the existing server-only account key. Bounds: 30-day TTL,
128 entries, 8 MiB ciphertext total, 2 MiB per entry, 12 MiB decoded JSON.
Expiration/eviction is request-driven. Cache entries are reproducible and may be
evicted sooner when full; credential rows are never evicted.

The production 3/min upstream admission window is encrypted inside `usage.admission` in
the existing vault and serialized under its advisory lock across deployments.
A replay-stage 540 persists a 60-second global pause as well as the existing
account hold. Cache hits do not call the game server and still work during that
pause. DB read/admission errors fail closed rather than sending uncapped calls.
Cache-write failure preserves a successful conversion and logs only its error
type. In-flight jobs and the optional FIFO queue remain process-local.
Durable cache reads use separate TLS SELECT connections and do not acquire the
authentication advisory lock or upstream worker/pending slots, so already-stored
replays remain available while the game server is busy. Visitor limits still apply.

For bounded deployment verification only, `PAIPU_REUSE_VALIDATION_ID` plus
`PAIPU_REUSE_VALIDATION_URLS` (exactly two official URLs separated by a newline)
tests two admitted replay fetches using one eligible slot. It never bypasses a
hold, stops at the first failure and durably claims the ID before I/O, preventing
repeats on restart. Clear both settings afterwards. Separately,
`PAIPU_REPLAY_CACHE_VALIDATION_DATABASE_URL` must name a different test branch;
it checks the real driver's encrypted cache roundtrip, TLS, RLS and restricted
role without reading or writing the authentication row. Clear after validation.

These changes reduce repeated authentication and replay retrieval. They do not
establish the provider's unpublished 540 quota or guarantee an account unblock.

Account slots 1–20 are supported. Configure `PAIPU_SERVICE_EMAIL_10` through
`PAIPU_SERVICE_EMAIL_20` and matching `PAIPU_SERVICE_REGION_N=jp` in Render;
each newly configured account still requires its own initial OTP enrollment.
Existing databases must run `sql/expand_session_vault.sql` as the owner before
enrolling additional slots. This only raises the encrypted row limit to 64 KiB.

`PAIPU_REPLAY_QUEUE_ENABLED=false` temporarily switches shared conversions to
synchronous requests. Serialization, cache, visitor limits and 3/min upstream
admission remain active; busy/held accounts return a response without a ticket
or background retry. Restore `true` to enable the FIFO queue.

An explicitly authorized one-shot replay diagnostic can be configured with
`PAIPU_REPLAY_DIAGNOSTIC_ID` (unique alphanumeric revision, at most 64 chars) and
`PAIPU_REPLAY_DIAGNOSTIC_URL` (official shared replay URL). It uses one authenticated
eligible account, respects all local/global holds, records the
normal outcome, and logs only stage/code or success/round count. A durable claim
prevents repeated calls on restart or overlapping deploys. It is off by default;
clear both settings after the diagnostic. Public requests cannot invoke it.

This is the single application directory used by the existing Render service.
See ../README.md for startup and AUTH_REVIEW.md for verification status.

## 공용 패보 조회 계정

서버 환경변수 `PAIPU_SERVICE_EMAIL`, `PAIPU_SERVICE_REGION`을 설정하면
운영자가 지정한 계정을 공용 패보 조회에 사용할 수 있습니다. 계정 이메일과
인증 정보는 공개 저장소에 적지 않습니다. 운영자는 `/?setup=1`에서 해당
이메일의 Yostar 인증을 한 번 완료합니다. 다른 이메일은 공용 계정으로
등록되지 않습니다. 방문자는 개인 로그인 없이 `/api/convert`를 사용합니다.
공용 계정은 패보 조회에만 사용하며 게임 플레이나 유료 분석을 실행하지 않습니다.

운영자 키를 확인한 공용 계정의 인증 메일 발송에는 사이트 자체의 시간당
이메일/IP 횟수 제한과 60초 재전송 대기를 적용하지 않습니다. Yostar의
발송 제한은 그대로 응답하며 자동 재발송은 하지 않습니다. 인증코드 입력은
브라우저·계정·지역별 15분당 8회로 계산하므로 여러 계정을 연속 등록할 수
있습니다. 임의 이메일로 보내는 개인 인증 요청에는 기존 발송 제한을 유지합니다.

개인 브라우저 세션의 로그아웃·만료는 공용 계정 세션과 분리됩니다. SDK
토큰 갱신은 계정별로 직렬화하며, 게임 조회가 실패해도 갱신된 SDK 토큰을
먼저 저장합니다. 공식 인증이 무효화되면 운영자 재인증이 필요합니다.

Render 무료 인스턴스에서는 외부 무료 PostgreSQL의 **직접 연결**을 사용합니다.
`sql/session_vault.sql`을 DB 소유자로 실행한 뒤 `paipu_runtime`에만 무작위
로그인 암호를 부여합니다. 이 역할은 비공개 스키마의 고정 계정 행을 읽고
암호문을 갱신할 수 있으며, 행 추가·삭제·DDL·관리 권한은 없습니다. RLS도
적용합니다. Render에는 `PAIPU_DATABASE_URL`과 `PAIPU_ACCOUNT_KEY`를
비밀 환경변수로 함께 설정합니다. DB 소유자 연결 문자열은 런타임에 사용하지
않습니다. 원격 DB는 TLS 인증서와 호스트를 검증합니다.

토큰·UID·기기 ID·이메일은 Fernet 인증 암호화 후 하나의 암호문으로 저장됩니다.
키는 Render에만 두고 DB에 저장하지 않습니다. DB는 앱 시작과 실제 인증/조회
요청에서만 연결하며, 타이머·공개 상태 API·헬스 체크로 깨우지 않습니다. 운영자가 계정 상태·통계를 확인할 때는 최신 저장 정보를 읽습니다. Neon Free의
사용량 한도와 무료 계정 여부를 확인한 후 연결해야 합니다. 유료 플랜·디스크는
필요하지 않습니다. 플러그인 계정 연결과 최초 OTP는 운영자가 완료해야 합니다.

조회 시 DB에서 최신 SDK 세션을 다시 읽습니다. PostgreSQL 세션 잠금으로
재배포 중 두 프로세스가 같은 토큰을 동시에 갱신하지 못하게 하고, 새 토큰을
autocommit으로 먼저 저장한 후 게임 서버를 호출합니다. 따라서 Neon의
`-pooler` 연결과 transaction pooler 6543 포트는 지원하지 않습니다. 연결은
조회가 끝나면 닫으며, 프로세스가 종료돼도 DB 연결 종료로 잠금이 해제됩니다.
외부 SDK의 토큰 발급과 DB 저장을 하나의 원자적 트랜잭션으로 묶을 수는 없으므로
그 두 동작 사이의 강제 종료/DB 장애까지 완전한 복원을 보장하지 않습니다.

DB 장애·복호화 실패 시 인증 정보 덮어쓰기/메모리 우회 로그인을 막고 503을
반환합니다. JSON 업로드와 프런트엔드는 계속 사용할 수 있습니다. 네트워크
오류나 분류되지 않은 SDK 오류를 만료로 단정해 토큰을 삭제하지 않습니다.
저장 세션으로 자동 인증이 계속 거부될 때 운영자 화면에서 재인증할 수 있습니다.
SDK 토큰의 보장 유효기간이나 무기한 로그인을 가정하지 않습니다.

다른 영구 파일시스템이 이미 있는 환경에서는 대신 `PAIPU_ACCOUNT_FILE`과
서버 비밀 환경변수 `PAIPU_ACCOUNT_KEY`를 함께 설정할 수 있습니다. 키는 Fernet
형식의 32바이트 암호화 키이며 코드나 Git에 기록하지 않습니다. 파일은
공개 폴더 외부에 저장하며 원자적으로 교체하고 권한 0600을 사용합니다.
키가 틀리거나 파일이 손상되면 임의 계정으로 진행하지 않고 복원에 실패합니다.

저장소 설정이 없으면 메모리 모드입니다. 메모리 모드는 방문자 로그인 없이
조회하는 흐름을 검증할 수 있지만 서버가 재시작되면 운영자 재인증이 필요합니다.
Render 무료 서비스의 로컬 파일은 영구 저장소가 아닙니다. 파일 경로만
설정해서는 재시작 복원이 보장되지 않으며 실제 영구 디스크를 연결해야 합니다.

회귀 검증: 공용 계정의 다른 이메일 등록 거부, 응답의 인증 정보 비노출,
브라우저 쿠키 없는 패보 조회, 개인 로그아웃 후 공용 조회 유지, 암호화 파일
재로드 및 SDK 토큰 갱신 후 저장을 stub provider로 검증합니다. 이 검증은
실제 공용 계정 인증 성공을 의미하지 않습니다.

PostgreSQL 단위 테스트는 DB를 모사하여 암호화·잠금·토큰 선저장·오래된
세션 재조회·오류 시 보존·503 비밀정보 비노출을 검증합니다. 별도의 실제
배포 검증 결과는 `SESSION_VERIFICATION.md`에 기록합니다. 모사 테스트와
실제 작혼 로그인 및 패보 조회 결과를 구분해야 합니다.

## v3.7.0 · iPhone 제출 안내 / 운영자 조회 통계

아이폰은 결과 URL 칸을 길게 눌러 전체 선택·복사한 후, 큰
**복사 없이 NAGA 열기** 링크로 이동합니다. 이 링크는 클립보드를 수정하지
않으며 분석 신청도 하지 않습니다. 아이폰에서는 자동 복사 버튼을 숨겨
직접 복사한 내용을 덮어쓰지 않도록 합니다. TXT 보기는 보조 기능입니다.

운영자 인증 후 **조회 계정 상태 확인**을 누르면 계정별 전체·오늘 조회
시도/성공/실패, 최근 시도·실패 시각, 최근 오류 코드, 진행 중·결과 미확인
횟수가 표시됩니다. 공개 상태 응답에는 통계를 포함하지 않습니다.

- 집계는 이 기능 적용 후 첫 실제 계정 조회부터 시작합니다. 과거 로그로
  전체 횟수를 복원하지 않습니다. 캐시 응답·중복 요청 합치기·대기열 확인·
  이메일 인증·JSON 파일 변환은 계정 조회로 세지 않습니다. 다른 계정으로
  재시도하면 각 계정에 한 번씩 집계됩니다.
- 오늘은 `Asia/Seoul` 기준입니다. 시도는 시작일, 성공/실패는 완료일에
  집계하므로 자정을 넘겨 처리하면 일별 시도 수와 완료 수가 다를 수 있습니다.
- 시도는 외부 호출 전에, 결과는 처리 후 저장합니다. 프로세스 강제 종료나
  결과 저장 실패로 완료 여부를 모르면 결과 미확인으로 남깁니다.
- 기존 Neon 암호문 행 안에 고정 크기 누적/오늘 카운터만 보관합니다.
  인증 토큰 갱신·재등록과 재배포 후에도 유지되며 새 테이블·유료 저장소·
  주기적 요청은 추가하지 않습니다. 모든 갱신은 기존 advisory lock으로
  직렬화합니다. 조회 계정 슬롯의 통계이므로 슬롯 이메일을 교체할 경우
  이전 계정의 누적 기록도 포함된다는 점에 유의합니다.
- 테스트: 재시작/동시 배포/540 실패 후 다른 계정 성공/주 계정 재인증/
  인증 지역 변경/한국시간 자정/암호문 크기 제한/공개 응답 비노출을 검증합니다.

## v3.7.2 · Android/PC 자동 복사

Android/PC에서는 `writeText` → `text/plain` ClipboardItem → 일반 텍스트
copy 이벤트 순으로 복사합니다. HTML 표현을 함께 쓰지 않아 수신 앱이 HTML을
일반 텍스트로 다시 변환하는 경로를 제거했습니다. iPhone은 기존 직접 선택·복사
경로를 계속 사용합니다. 다른 기기에서도 자동 복사가 실패하면 직접 복사 안내를
이용할 수 있습니다. 복사 확인은 개행이 공백·탭으로 바뀐 경우도 구분합니다.

네이티브 Android/Safari 기기에서의 최종 붙여넣기는 장치별 확인이 필요합니다.
Clipboard API의 성공 응답만으로 수신 앱의 개행 보존을 보장하지 않습니다.

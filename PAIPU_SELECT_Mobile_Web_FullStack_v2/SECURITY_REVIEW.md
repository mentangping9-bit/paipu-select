# Final security review — 2026-10-20

Scope: application source, authentication routes, durable session adapter,
public static files, browser rendering, upstream URL boundaries and installed
Python dependencies. This is an application review, not an independent
penetration test or a guarantee against unknown vulnerabilities.

## Corrected findings

- **Unprotected service authentication management:** a public caller could
  request verification emails for the configured service account. When a
  service account is configured, all authentication mutation routes now require
  a separate high-entropy operator key. This also covers the alternate email
  request shape, OTP verification and logout. Missing configuration fails
  closed. Public replay retrieval still uses the configured server-only
  account, without providing clients arbitrary game API access or credentials.
- **Unbounded handler creation and slow requests:** handler concurrency is
  bounded, socket reads time out, request bodies remain bounded, conflicting
  framing is rejected and the rate-limit map has a bounded size. Overload is
  exercised locally; production is not load-tested.
- **Missing browser response policies:** self-only scripts/styles/connections,
  no inline script/style permission, frame denial, no referrer, restricted
  browser capabilities and HTTPS HSTS are applied. Static GET and HEAD use an
  explicit public-file boundary; directory listings and source/config paths
  are unavailable. Request logs omit query strings and request bodies.
- **Old installer advisories:** pin pip 26.2.1. After updating the local runtime
  environment, pip-audit reported no known vulnerabilities among packages it
  could audit. The pinned Git converter is not in PyPI and cannot be covered by
  this automated check; its integration and bundled authentication helpers
  were reviewed separately. The scan is time-specific, not a future guarantee.

- **Runtime security patches:** specify Python 3.12.15, the upstream security
  release published 2026-09-30, preserving the existing 3.12 interpreter family.
  Verify the actual Render interpreter from startup logs, not only YAML.

## Preserved protections

- Fernet-authenticated session encryption; encryption key is separate in Render.
- Direct PostgreSQL certificate/hostname verification and channel binding.
- Restricted database role and fixed-row RLS, parameterized SQL and advisory
  locking around session refresh. Downstream errors do not discard a committed
  rotated token.
- API responses and logs exclude OTP values, SDK tokens, database credentials,
  service email and operator keys. The operator's own session status is private
  to its HttpOnly cookie. Production cookies use Secure and SameSite=Lax.
- Exact official replay-host validation; replay text is reduced to an ID,
  rather than fetched as a user-supplied arbitrary URL. Upstream record
  downloads reject local/untrusted addresses and redirects and enforce bounds.
- Replay names/results are rendered with textContent. Uploaded JSON stays in
  the browser. UI language storage contains only the language preference.

## Operator recovery

The added `PAIPU_OPERATOR_KEY` is a separate Render secret, not the session
cipher key. Normal visitors do not need it. For future account reauthentication,
the Render service owner can retrieve the value from Environment, open
`/?setup=1`, enter the operator key in its password field and complete Yostar
email verification. The UI sends the key only in authentication request headers,
never in URLs or persistent browser storage, and clears the field on pagehide.

Both Render and Neon remain on free plans. No disk, keep-awake job or paid
resource was added. Large distributed denial-of-service protection and provider
account security remain infrastructure/provider responsibilities.

## Verification

Security regressions cover denied anonymous/wrong-key auth mutations, preserved
public replay access, fail-closed key configuration, browser policies, private
path rejection, cross-site requests, invalid/oversized bodies, conflicting
framing, bounded rate state, and actual local overload/recovery. Existing
session encryption, token rotation, JSON/scoring and three-language checks are
retained. After deployment, verify the exact health commit, denied anonymous
management requests, public response policies and actual JP/KR replay retrieval;
source tests alone do not establish deployed behavior. No NP analysis is sent.

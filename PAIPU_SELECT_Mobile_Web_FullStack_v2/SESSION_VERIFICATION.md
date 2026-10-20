# Durable service-account session verification

Verified on 2026-10-20. No account identifier, OTP, SDK token, DB password or
encryption key is included here.

## Infrastructure and security

- Existing Render service remains on the free plan; no disk was purchased.
- Neon organization plan was confirmed as `free` before creating a dedicated
  project in Oregon. Production and validation use separate database branches
  and separate runtime passwords.
- Production secrets are configured in Render environment variables. The
  database stores only a Fernet-authenticated ciphertext containing the SDK
  session. The encryption key is not stored in the database or repository.
- The runtime role has no administrator/bypass-RLS/create-role/create-database
  privileges and no inherited memberships. Public access to the private schema
  and table is revoked. The role can select the fixed row and update ciphertext
  and its timestamp; it cannot insert/delete rows or modify the account key.
- Direct PostgreSQL TLS uses `verify-full`, an explicit certifi CA bundle,
  and the provider-required channel binding. The initial Render failure was
  diagnosed as certificate verification failure in the bundled libpq trust
  lookup; certificate verification was retained when correcting CA discovery.
- No keep-awake requests or token-refresh scheduler exists. An idle Neon
  production compute was observed in the `idle` state during validation.

## Completed live checks

| Check | Evidence |
| --- | --- |
| Actual PostgreSQL encryption / TLS / restricted role / RLS | Opt-in Render verification passed on an isolated branch |
| Restore a rotated sample token in a new Python process | Passed against actual PostgreSQL |
| Exclude a second connection while refreshing | Actual advisory-lock timeout passed |
| Preserve a committed rotated token after downstream failure | Passed against actual PostgreSQL |
| First service-account enrollment | Production ciphertext present; SDK/game retrieval confirmed |
| Cookie-free Korean Mahjong Soul replay request | HTTP 200; 10 rounds, 8 wins, no unknown endings |
| New Render instance, same commit, no email verification | Restored shared session and fetched the same 10 rounds with identical game logs |

The live storage checks ran on commit `74fc6dc55e25a4d71eca04968396a74d590ab30d`,
deploy `dep-dbbgm4mk1f9s73bqstng`. After success,
`PAIPU_VALIDATION_DATABASE_URL` was cleared. Synthetic validation data was
removed and the test branch has an expiry; normal restarts do not rerun it.

The same-commit instance replacement was deploy `dep-dbbh440m7kps73evojh0`.
Immediately afterward, anonymous status reported `shared_ready=true`,
`shared_game_authenticated=false`, and `encrypted_postgres`. A new replay
request then returned HTTP 200 using the restored SDK session. The previous
browser login was not needed.

## Scope and ongoing verification

The source release also hides the login panel until authentication status is
known, avoiding a misleading login-form flash. After its GitHub-triggered
deployment, verify the exact health commit and perform another cookie-free
replay fetch; the deploy's `live` status alone is insufficient.

No guaranteed SDK token lifetime or perpetual login policy has been established.
Automatic authentication uses the existing `user/quick-login` endpoint. A saved
session rejected persistently by Yostar requires operator reauthentication.
Network errors, malformed responses and unclassified provider errors preserve
stored credentials instead of declaring them expired or deleting them.

The cross-service SDK rotation and database write cannot be one atomic
transaction. Forced termination between those operations can still require
reauthentication. Free-tier quotas can limit availability; no paid upgrades or
automatic paid resource provisioning were configured.

This does not claim a physical mobile-browser process shutdown test, or actual
NAGA paid-analysis receipt. No NP was spent by this implementation or checks.

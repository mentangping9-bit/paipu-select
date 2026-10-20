# Replay queue and account pool — 3.3.0

These are application operating settings, not a provider-approved quota or a
promise that a Mahjong Soul account/IP can never be restricted.

| Control | Default |
| --- | --- |
| Actual replay jobs across all accounts/visitors | 10 starts per rolling minute; at least 6 seconds apart |
| Active upstream job | 1 |
| Accepted distinct jobs including the active one | 20, in FIFO order |
| Per browser | 1 pending distinct replay; 12 submissions/minute, 120/hour |
| Additional visitors requesting the same replay | Up to 8, sharing the job |
| Status polling | Every 2 seconds; no game-server requests |
| Pending deadline | 30 minutes, then an explicit expiry response |
| Completed ticket retention | 10 minutes; 64 jobs, 256 tickets, 8 MiB of results |
| Successful replay cache | 15 minutes; 64 records, 8 MiB total, 2 MiB/record |

POST /api/convert returns cached JSON immediately (200), or a private job ticket
(202). GET /api/convert/status?job=... reports queued position, minimum interval
wait, processing, completed JSON, or a classified error. The opaque ticket is
bound to the signed HttpOnly/SameSite browser visitor cookie. Another visitor
cannot read a job even with its ticket. Public status contains no email, SDK
credentials, provider response dump or account identity.

One bounded in-process thread performs queued work. HTTP handlers are never
held open for queue waiting. The thread exits when the queue empties; no cron,
keep-alive traffic, additional Render worker service or paid resource is used.
Polling never consumes a submission or game-server quota. Repeated successful
replays use the canonical region/replay-ID cache; share captions, viewer suffixes
and alternate official hosts do not force extra upstream requests.

## Account pool and upstream 540

Up to three explicitly configured and officially authenticated accounts are
used in round-robin order. PAIPU_SERVICE_EMAIL is the existing primary, and
PAIPU_SERVICE_EMAIL_2/_3 enable additional slots using the existing KR/JP/EN
account region setting. The operator selects the slot before requesting and
verifying its first email OTP. Slot mutation remains protected by the operator
key. An email address alone does not authenticate an account.

All profiles share the existing restricted Postgres row, Fernet encryption and
cross-process advisory lock. Primary token replacement preserves secondary
profiles. Existing primary data loads without a migration or credential reset.
No email/token is committed. Additional slots require the encrypted DB backend.

A fetch-record 540 means the provider's replay retrieval limit was exceeded.
The affected account pauses for 10 minutes, persisted with its encrypted session.
The entire queue pauses at least 60 seconds before a retry, even if another
account is ready. If all authenticated accounts are resting, the queue waits
until the earliest account is eligible. The same accepted job can try at most
three provider calls, then returns an explicit limitation message. No tight
retry loop, IP rotation, refresh-token guessing or automatic reauthentication.
These pauses are conservative application choices, NOT a statement about
Mahjong Soul's actual reset time. An IP-wide or longer restriction can persist
across all three accounts; changing accounts cannot guarantee its removal.

Queue/cache/counters are memory-only and reset on service replacement. Tickets
from an old instance return an expiry response and the user can resubmit.
Account credentials AND account cooldown timestamps are restored from Neon.
The deployment remains one free Render instance. Limits are process-local, not
distributed DDoS protection. JSON import/round selection/URL output remain local
and do not consume game-server quotas.

Verification uses fake clocks/providers to check the 11th distinct job waits,
FIFO order, same-replay coalescing, 540 pauses/retry bounds, ticket ownership,
expiry, memory bounds, primary/secondary token preservation and restored
cooldowns. Live verification must not generate 11 upstream calls merely to test
the limiter. Actual login for additional accounts is unverified until their
first email authentication and a real game-server fetch have completed.

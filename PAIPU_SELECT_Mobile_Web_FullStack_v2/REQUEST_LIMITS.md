# Replay request admission — 3.2.2

The public shared-account replay endpoint applies the following application
limits. They are our operating settings, not a provider-approved safe quota.
No account rotation, IP rotation or bypass of upstream restrictions is used.

| Control | Default |
| --- | --- |
| Per browser | 12 valid replay requests per rolling minute; 120 per rolling hour |
| Actual shared-account replay jobs | 20 starts per rolling minute across visitors |
| Simultaneous upstream replay jobs | 1 |
| Pending distinct replay jobs | At most 5 total: 1 active and up to 4 waiting |
| Wait for a processing slot | Up to 20 seconds, then a retry response |
| Identical simultaneous replay requests | Share one result; up to 8 additional waiting handlers |
| Successful replay cache | 15 minutes, 64 entries, at most 8 MiB total and 2 MiB per entry |

The existing limit keyed by `client_address` is replaced for public replay
requests. A reverse proxy can make unrelated visitors have the same socket
address. Instead, an opaque HMAC-signed HttpOnly/SameSite browser cookie identifies
the requesting browser, while the global upstream limiter protects the shared
account even if a caller clears or does not retain cookies. Visitor state is
bounded to 4096 entries and does not store IP addresses or game credentials.

Successful results are keyed by the parsed replay ID and account region, so
captions, alternate official hosts and viewer suffixes do not force another
upstream lookup. Errors are never cached. Cached results and joined requests do
not consume another upstream job slot or start quota, but still count toward
that browser's request limit. An in-progress new replay from the same browser
cannot queue additional different replay jobs. JSON-file import, round selection,
URL generation and normal page/status requests do not consume replay quotas.

Busy responses use HTTP 503; excessive browser/global starts use HTTP 429.
Both include `Retry-After` and a numeric `retry_after`. The UI explains whether
the service is busy or that browser made repeated requests, and temporarily
shows a translated countdown on the convert button. It never automatically
retries a replay request. The client timeout accommodates bounded queue waiting.

The cache and counters are in-process, and reset on Render instance replacement;
they are not distributed DDoS protection. The deployed service has one instance.
The existing database advisory lock still serializes SDK rotation across old/new
deployments. Encrypted session persistence in Neon remains independent of this
nonpersistent cache; no paid storage or background/keep-awake jobs are added.

Tests use fake providers and concurrent local requests to verify cache isolation,
expiry, coalescing, per-browser/global windows, busy/timeout recovery, bounded
memory, signed cookies, Retry-After and independent visitors on the same proxy
address. Live checks should use the same cached replay for rate-limit testing,
so testing the limiter does not itself flood Mahjong Soul.

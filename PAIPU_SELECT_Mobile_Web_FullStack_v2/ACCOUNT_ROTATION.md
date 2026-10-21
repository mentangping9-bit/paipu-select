# Shared replay accounts and visible queue

- Successfully enrolled SDK sessions stay encrypted in the existing vault.
  Real replay requests refresh their SDK session when needed; no background
  logins, OTP sending, or keepalive traffic is introduced.
- Ready accounts rotate in slot order 1–9 and wrap around. An account under a
  provider hold or with a known game-authentication failure is skipped. Existing
  preference for accounts without a known 540 hold is retained.
- Each queued replay tracks failed slots independently and never retries the
  same slot. Account-related failures can try up to nine configured slots.
  Game auth/unbound failures stay disabled until operator reauthentication.
- SDK API rejections preserve tokens and rest that slot for five minutes.
  Network/timeout failures rest it for one minute. No unknown provider error
  code is treated as proof of token expiration.
- Bad replay links, shared client/protocol failures, and database failures are
  returned directly; account switching does not repair them.
- Overall retrieval starts remain capped at 10 per rolling minute, spaced at
  least six seconds apart, with a single FIFO worker. Retries count too.
- A 540 response still pauses the entire queue for at least 60 seconds and
  retains the existing persisted per-account 10/30/60 minute hold. One job
  stops after three 540 responses, or earlier if all available slots failed.
  Rotation never clears a provider hold. Errors cannot be guaranteed absent.
- Waiting users see their own position, total waiting jobs, current processing
  count, and retry/pause state. Status polling makes no upstream requests.
  Queue tickets remain bound to their visitor; no other visitor's link, email,
  token, or result is exposed. Duplicated replays share one retrieval.
- The bounded queue accepts up to 100 distinct jobs, with the existing 256
  ticket ceiling and one pending replay per visitor retained.
- Queue state remains memory-only and expires after a bounded wait; it is
  independent from durable account sessions. Deploys discard pending jobs.

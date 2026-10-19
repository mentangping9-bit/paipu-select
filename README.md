# PAIPU SELECT

Mobile/desktop Mahjong Soul replay selection for NAGA custom analysis.
The single application directory is `PAIPU_SELECT_Mobile_Web_FullStack_v2`.
Both `python server.py` from the repository root and from that directory start
that same application. Render currently uses that directory as its Root Directory.

## Run

    python -m pip install -r requirements.txt
    python server.py

Open http://localhost:8765. Reviewed converter helper code is bundled, with its
MIT license, rather than importing an unpinned Git main branch at runtime.
Render's old extra install command is redundant; the bundled namespace prevents
it from replacing the reviewed helpers. The tracked render.yaml pins that extra
installation for future blueprint syncs.

## Verification

See `PAIPU_SELECT_Mobile_Web_FullStack_v2/AUTH_REVIEW.md` for exact verified and
unverified boundaries. `/api/health` reports the executing source commit, version,
and the separate unauthenticated gateway probe result. Version names do not
indicate successful account login.

Yostar credentials stay only in the server's memory for a two-hour idle session.
Restarting Render clears sessions and requires a new email verification.
No password is requested. NAGA's final paid submission remains under user control.

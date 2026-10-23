-- Run as the owner after validating on an isolated branch. No auth-row changes.
BEGIN;
CREATE TABLE IF NOT EXISTS paipu_private.replay_cache (
    cache_key text PRIMARY KEY CHECK (cache_key ~ '^[0-9a-f]{64}$'),
    ciphertext text NOT NULL CHECK (length(ciphertext)<=2097152),
    cached_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS replay_cache_expires_at ON paipu_private.replay_cache(expires_at);
REVOKE ALL ON paipu_private.replay_cache FROM PUBLIC;
GRANT SELECT,INSERT,UPDATE,DELETE ON paipu_private.replay_cache TO paipu_runtime;
ALTER TABLE paipu_private.replay_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE paipu_private.replay_cache FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='paipu_private'
                   AND tablename='replay_cache' AND policyname='paipu_runtime_cache') THEN
        CREATE POLICY paipu_runtime_cache ON paipu_private.replay_cache TO paipu_runtime
            USING (true) WITH CHECK (true);
    END IF;
END $$;
COMMIT;

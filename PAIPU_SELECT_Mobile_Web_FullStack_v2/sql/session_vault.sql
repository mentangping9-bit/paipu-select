-- Run once as the database owner. No email, tokens or keys belong in this file.
-- Give paipu_runtime a randomly generated LOGIN password through the provider's
-- secret administration channel, then store its direct TLS DSN only in Render.
BEGIN;
CREATE SCHEMA IF NOT EXISTS paipu_private;
REVOKE ALL ON SCHEMA paipu_private FROM PUBLIC;
CREATE TABLE IF NOT EXISTS paipu_private.service_sessions (
    account_key text PRIMARY KEY CHECK (account_key = 'majsoul'),
    ciphertext text CHECK (length(ciphertext) <= 16384),
    updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO paipu_private.service_sessions (account_key) VALUES ('majsoul')
ON CONFLICT (account_key) DO NOTHING;
REVOKE ALL ON TABLE paipu_private.service_sessions FROM PUBLIC;
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'paipu_runtime') THEN
        CREATE ROLE paipu_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOREPLICATION NOBYPASSRLS;
    END IF;
END $$;
GRANT USAGE ON SCHEMA paipu_private TO paipu_runtime;
GRANT SELECT ON paipu_private.service_sessions TO paipu_runtime;
GRANT UPDATE (ciphertext, updated_at) ON paipu_private.service_sessions TO paipu_runtime;
ALTER TABLE paipu_private.service_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE paipu_private.service_sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS paipu_runtime_session ON paipu_private.service_sessions;
CREATE POLICY paipu_runtime_session ON paipu_private.service_sessions TO paipu_runtime
    USING (account_key = 'majsoul') WITH CHECK (account_key = 'majsoul');
COMMIT;

-- Non-destructive capacity increase for 20 encrypted account slots.
-- Keep the singleton row, ciphertext, RLS and runtime-role privileges intact.
BEGIN;
ALTER TABLE paipu_private.service_sessions
    DROP CONSTRAINT service_sessions_ciphertext_check,
    ADD CONSTRAINT service_sessions_ciphertext_check CHECK (length(ciphertext) <= 65536);
COMMIT;

-- Corrective migration only. Do not rewrite old migration or delete legacy rows.
-- PostgreSQL 17 provides gen_random_uuid() without adding pgcrypto.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'conversations_user_id_auth_users_fkey'
          AND conrelid = 'public.conversations'::regclass
    ) THEN
        ALTER TABLE public.conversations
            ADD CONSTRAINT conversations_user_id_auth_users_fkey
            FOREIGN KEY (user_id)
            REFERENCES auth.users(id)
            ON DELETE CASCADE
            NOT VALID;
    END IF;
END $$;

ALTER TABLE public.messages
    DROP CONSTRAINT IF EXISTS messages_role_check;

ALTER TABLE public.messages
    ADD CONSTRAINT messages_role_check
    CHECK (role IN ('user', 'assistant'))
    NOT VALID;

-- Validate later after checking/remediating any legacy rows:
-- ALTER TABLE public.conversations VALIDATE CONSTRAINT conversations_user_id_auth_users_fkey;
-- ALTER TABLE public.messages VALIDATE CONSTRAINT messages_role_check;

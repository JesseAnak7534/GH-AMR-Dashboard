-- Close anonymous REST access to every table in the public schema.
--
-- Supabase serves the public schema through PostgREST. With row level security
-- disabled, the anon key could read every table over HTTPS. That key is public
-- by design -- it is meant to be embedded in client applications -- so this was
-- not a theoretical exposure. Verified before the fix: an unauthenticated
-- request returned rows from samples, ast_results and users, the last including
-- the email and bcrypt password_hash columns.
--
-- Enabling RLS with no policy denies all access to the anon and authenticated
-- roles. The application is unaffected: it connects over Postgres as the table
-- owner, and an owner bypasses RLS unless FORCE ROW LEVEL SECURITY is set,
-- which it is not.
--
-- If a public read-only view is wanted later, add an explicit policy to the
-- specific tables and columns intended for it. Do not disable this.
DO $$
DECLARE
    target text;
BEGIN
    FOR target IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
          AND NOT c.relrowsecurity
        ORDER BY c.relname
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', target);
        RAISE NOTICE 'row level security enabled on %', target;
    END LOOP;
END
$$;

-- ============================================================
-- MediExplain AI — Migration 003: Profiles Security Hardening
-- File: supabase/migrations/003_profiles_security_hardening.sql
-- Description:
--   1. Eliminates infinite recursion (Error 42P17) in profiles RLS
--      via a SECURITY DEFINER admin check function.
--   2. Enforces column-level UPDATE restrictions to prevent
--      privilege escalation (is_admin) and identity tampering (id, email).
--   3. Implements defense-in-depth trigger protection on sensitive fields
--      with robust role detection and spoofing prevention.
--   4. Preserves full legitimate service-role and user access.
-- ============================================================

-- ============================================================
-- 1. SECURE ADMIN-CHECK FUNCTION (SECURITY DEFINER)
-- Bypasses RLS safely to prevent policy recursion (Error 42P17).
-- ============================================================

CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
STABLE
AS $$
DECLARE
    _uid UUID;
    _admin BOOLEAN;
BEGIN
    _uid := auth.uid();
    IF _uid IS NULL THEN
        RETURN FALSE;
    END IF;

    -- Directly check is_admin from public.profiles.
    -- Because this function is SECURITY DEFINER with a fixed search_path,
    -- it executes with the database owner's privileges (postgres),
    -- which bypasses RLS and permanently eliminates infinite recursion (42P17).
    SELECT is_admin INTO _admin
    FROM public.profiles
    WHERE id = _uid;

    RETURN COALESCE(_admin, FALSE);
END;
$$;

-- Restrict function execution: revoke from PUBLIC, grant only to authenticated and service_role
REVOKE ALL ON FUNCTION public.is_admin() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.is_admin() TO authenticated, service_role;

-- ============================================================
-- 2. HARDEN RLS POLICIES ON public.profiles
-- ============================================================

-- Fix Admin SELECT Policy: Use the non-recursive public.is_admin() function
DROP POLICY IF EXISTS "Admins read all profiles" ON public.profiles;
CREATE POLICY "Admins read all profiles"
    ON public.profiles FOR SELECT
    TO authenticated
    USING (public.is_admin());

-- Harden User UPDATE Policy: Ensure row ownership and matching check
DROP POLICY IF EXISTS "Users update own profile" ON public.profiles;
CREATE POLICY "Users update own profile"
    ON public.profiles FOR UPDATE
    TO authenticated
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- Ensure RLS remains enabled on profiles
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- 3. COLUMN-LEVEL PERMISSION HARDENING (GRANT / REVOKE)
-- Prevents clients from updating is_admin, id, email, created_at
-- ============================================================

-- Revoke table-level write operations from untrusted client roles
REVOKE INSERT, UPDATE, DELETE ON public.profiles FROM anon, authenticated;

-- Allow authenticated and anon users to read profiles (subject to RLS policies)
GRANT SELECT ON TABLE public.profiles TO anon, authenticated;

-- Grant UPDATE ONLY on explicitly approved user-editable profile columns
GRANT UPDATE (display_name, avatar_url) ON public.profiles TO authenticated;

-- Ensure service_role maintains full unrestricted access for backend operations
GRANT ALL ON TABLE public.profiles TO service_role;

-- ============================================================
-- 4. DEFENSE-IN-DEPTH TRIGGER ENFORCEMENT
-- Blocks unauthorized tampering with sensitive fields even if
-- column-level grants are inadvertently relaxed in the future.
-- ============================================================

CREATE OR REPLACE FUNCTION public.protect_profiles_sensitive_columns()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    _new JSONB;
    _old JSONB;
    _jwt_role TEXT;
    _effective_role TEXT;
    _is_privileged BOOLEAN;
BEGIN
    -- 1. Extract role from JWT claim safely, converting empty string to NULL
    --    so empty claims do not prevent fallback checks.
    _jwt_role := NULLIF(current_setting('request.jwt.claim.role', true), '');

    -- 2. Determine effective role with strict fallback order
    _effective_role := COALESCE(
        _jwt_role,
        NULLIF(auth.role(), ''),
        current_user
    );

    -- 3. Determine if the execution context is genuinely privileged:
    --    - Must have an active PostgreSQL role of service_role, postgres, or supabase_admin.
    --    - AND the effective role must be privileged.
    --    - AND auth.uid() must be NULL (ensuring an authenticated user session
    --      cannot claim service_role status while holding a user token).
    _is_privileged := (
        _effective_role IN ('service_role', 'postgres', 'supabase_admin')
        AND current_user IN ('service_role', 'postgres', 'supabase_admin')
        AND auth.uid() IS NULL
    );

    -- If genuinely privileged (backend service-role or database administrator), allow update
    IF _is_privileged THEN
        RETURN NEW;
    END IF;

    -- Otherwise, enforce strict sensitive-column protections
    _new := to_jsonb(NEW);
    _old := to_jsonb(OLD);

    -- Guard 1: Prevent changing primary identity key (id)
    IF _new->>'id' IS DISTINCT FROM _old->>'id' THEN
        RAISE EXCEPTION 'Modifying profile id is forbidden.'
            USING ERRCODE = '42501';
    END IF;

    -- Guard 2: Prevent changing primary email directly
    IF _new->>'email' IS DISTINCT FROM _old->>'email' THEN
        RAISE EXCEPTION 'Modifying profile email directly is forbidden. Updates must go through auth service.'
            USING ERRCODE = '42501';
    END IF;

    -- Guard 3: Prevent privilege escalation via is_admin
    IF _new->>'is_admin' IS DISTINCT FROM _old->>'is_admin' THEN
        RAISE EXCEPTION 'Modifying is_admin privilege is forbidden.'
            USING ERRCODE = '42501';
    END IF;

    -- Guard 4: Prevent altering audit timestamp (created_at)
    IF _new->>'created_at' IS DISTINCT FROM _old->>'created_at' THEN
        RAISE EXCEPTION 'Modifying profile created_at timestamp is forbidden.'
            USING ERRCODE = '42501';
    END IF;

    -- Guard 5: Prevent altering normalized_email if present
    IF _new ? 'normalized_email' AND (_new->>'normalized_email' IS DISTINCT FROM _old->>'normalized_email') THEN
        RAISE EXCEPTION 'Modifying normalized_email is forbidden.'
            USING ERRCODE = '42501';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_protect_profiles_sensitive_columns ON public.profiles;
CREATE TRIGGER trg_protect_profiles_sensitive_columns
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW
    EXECUTE FUNCTION public.protect_profiles_sensitive_columns();

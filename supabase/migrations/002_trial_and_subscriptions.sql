-- ============================================================
-- MediExplain AI — Phase 6 Migration: Trial & Subscription Management
-- File: supabase/migrations/002_trial_and_subscriptions.sql
-- ============================================================

-- 1. Add normalized_email column to profiles for duplicate trial detection
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS normalized_email TEXT;

-- Populate existing profiles' normalized_email
UPDATE public.profiles
SET normalized_email = LOWER(
    CASE 
        WHEN email LIKE '%@gmail.com' THEN 
            REGEXP_REPLACE(SPLIT_PART(SPLIT_PART(email, '@', 1), '+', 1), '\.', '', 'g') || '@gmail.com'
        WHEN email LIKE '%@googlemail.com' THEN 
            REGEXP_REPLACE(SPLIT_PART(SPLIT_PART(email, '@', 1), '+', 1), '\.', '', 'g') || '@gmail.com'
        ELSE 
            TRIM(LOWER(email))
    END
)
WHERE normalized_email IS NULL;

-- Create index on normalized_email
CREATE INDEX IF NOT EXISTS idx_profiles_normalized_email ON public.profiles(normalized_email);

-- 2. Update subscription_status check constraint to support canonical status names:
--    'TRIAL_ACTIVE', 'ACTIVE', 'PAST_DUE', 'CANCELED', 'EXPIRED'
--    as well as existing legacy status names.
ALTER TABLE public.subscriptions 
    DROP CONSTRAINT IF EXISTS subscriptions_subscription_status_check;

ALTER TABLE public.subscriptions
    ADD CONSTRAINT subscriptions_subscription_status_check
    CHECK (subscription_status IN (
        'TRIAL_ACTIVE',
        'TRIAL_EXPIRED',
        'AUTHORIZATION_PENDING',
        'ACTIVE',
        'PAYMENT_PENDING',
        'PAYMENT_FAILED',
        'PAST_DUE',
        'CANCELLED',
        'CANCELED',
        'HALTED',
        'EXPIRED'
    ));

-- 3. Update handle_new_user() to populate normalized_email and enforce duplicate trial protection
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
    norm_email TEXT;
    prior_account_count INTEGER;
BEGIN
    -- Compute normalized email:
    -- Restrict dot and plus-tag normalization strictly to Gmail / Googlemail
    -- For all other email providers (Yahoo, Outlook, unknown), preserve address exactly
    norm_email := LOWER(
        CASE 
            WHEN NEW.email LIKE '%@gmail.com' THEN 
                REGEXP_REPLACE(SPLIT_PART(SPLIT_PART(NEW.email, '@', 1), '+', 1), '\.', '', 'g') || '@gmail.com'
            WHEN NEW.email LIKE '%@googlemail.com' THEN 
                REGEXP_REPLACE(SPLIT_PART(SPLIT_PART(NEW.email, '@', 1), '+', 1), '\.', '', 'g') || '@gmail.com'
            ELSE 
                TRIM(LOWER(NEW.email))
        END
    );

    -- Check if normalized email has already been registered by a different account
    SELECT COUNT(*) INTO prior_account_count
    FROM public.profiles
    WHERE normalized_email = norm_email AND id != NEW.id;

    -- Create profile
    INSERT INTO public.profiles (id, email, display_name, normalized_email)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
        norm_email
    )
    ON CONFLICT (id) DO UPDATE SET
        normalized_email = norm_email;

    -- Allocate subscription
    IF prior_account_count > 0 THEN
        -- Duplicate account detected: do NOT give another 30-day free trial
        INSERT INTO public.subscriptions (
            user_id,
            trial_start_date,
            trial_end_date,
            subscription_status
        )
        VALUES (
            NEW.id,
            NOW(),
            NOW(), -- Expired immediately
            'EXPIRED'
        )
        ON CONFLICT (user_id) DO NOTHING;

        -- Log audit record
        INSERT INTO public.subscription_events (
            subscription_id,
            event_type,
            gateway_event_id,
            payload
        )
        SELECT s.id, 'TRIAL_DUPLICATE_PREVENTED', 'dup_prev_' || NEW.id::text, jsonb_build_object('normalized_email', norm_email, 'user_id', NEW.id)
        FROM public.subscriptions s
        WHERE s.user_id = NEW.id;
    ELSE
        -- Eligible for standard 30-day trial
        INSERT INTO public.subscriptions (
            user_id,
            trial_start_date,
            trial_end_date,
            subscription_status
        )
        VALUES (
            NEW.id,
            NOW(),
            NOW() + INTERVAL '30 days',
            'TRIAL_ACTIVE'
        )
        ON CONFLICT (user_id) DO NOTHING;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 4. Ensure gateway_event_id allows internal non-gateway events if needed
ALTER TABLE public.subscription_events 
    ALTER COLUMN gateway_event_id DROP NOT NULL;



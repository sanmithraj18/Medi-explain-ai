-- ============================================================
-- MediExplain AI — Initial Database Schema
-- Migration: 001_initial_schema.sql
-- Run this in your Supabase SQL Editor
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================
-- TABLE: profiles
-- Auto-created when a user verifies their email (via trigger)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.profiles (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name    TEXT,
    email           TEXT NOT NULL,
    avatar_url      TEXT,
    is_admin        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: subscriptions
-- One row per user — status tracks the full lifecycle
-- ============================================================
CREATE TABLE IF NOT EXISTS public.subscriptions (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    plan_name                   TEXT NOT NULL DEFAULT 'MediExplain AI Premium',
    amount                      INTEGER NOT NULL DEFAULT 20000,  -- in paise (₹200)
    currency                    TEXT NOT NULL DEFAULT 'INR',
    -- Trial
    trial_start_date            TIMESTAMPTZ,
    trial_end_date              TIMESTAMPTZ,
    -- Subscription status
    subscription_status         TEXT NOT NULL DEFAULT 'TRIAL_ACTIVE'
                                    CHECK (subscription_status IN (
                                        'TRIAL_ACTIVE',
                                        'TRIAL_EXPIRED',
                                        'AUTHORIZATION_PENDING',
                                        'ACTIVE',
                                        'PAYMENT_PENDING',
                                        'PAYMENT_FAILED',
                                        'CANCELLED',
                                        'HALTED',
                                        'EXPIRED'
                                    )),
    -- Razorpay fields (null until user starts subscription)
    gateway_subscription_id     TEXT UNIQUE,
    billing_start_date          TIMESTAMPTZ,
    next_billing_date           TIMESTAMPTZ,
    cancellation_date           TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id)
);

-- ============================================================
-- TABLE: medical_reports
-- Stores metadata about uploaded reports (file in Storage)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.medical_reports (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    report_name         TEXT NOT NULL,
    file_path           TEXT NOT NULL,          -- path in Supabase Storage
    file_type           TEXT NOT NULL           -- 'pdf', 'jpg', 'png'
                            CHECK (file_type IN ('pdf', 'jpg', 'jpeg', 'png')),
    file_size_bytes     BIGINT,
    raw_extracted_text  TEXT,                   -- Original preserved raw OCR/digital text for verification
    upload_date         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processing_status   TEXT NOT NULL DEFAULT 'PENDING'
                            CHECK (processing_status IN (
                                'PENDING',
                                'EXTRACTING',
                                'EXTRACTED',
                                'ANALYZING',
                                'COMPLETED',
                                'FAILED',
                                'NEEDS_REVIEW'
                            )),
    processing_error    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: extracted_parameters
-- Individual lab test rows extracted from a report
-- ============================================================
CREATE TABLE IF NOT EXISTS public.extracted_parameters (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id               UUID NOT NULL REFERENCES public.medical_reports(id) ON DELETE CASCADE,
    parameter_name          TEXT NOT NULL,
    observed_value          TEXT NOT NULL,      -- stored as text to preserve original
    unit                    TEXT,
    reference_min           NUMERIC,
    reference_max           NUMERIC,
    reference_text          TEXT,               -- original reference range string
    laboratory_flag         TEXT,               -- 'H', 'L', 'HH', 'LL', 'N', 'CRITICAL', or NULL
    extraction_confidence   NUMERIC             -- 0.0 to 1.0
                                CHECK (extraction_confidence IS NULL
                                    OR (extraction_confidence >= 0 AND extraction_confidence <= 1)),
    needs_user_review       BOOLEAN NOT NULL DEFAULT FALSE,
    user_confirmed          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: report_analyses
-- AI-generated explanation stored as structured JSON
-- ============================================================
CREATE TABLE IF NOT EXISTS public.report_analyses (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id               UUID NOT NULL REFERENCES public.medical_reports(id) ON DELETE CASCADE,
    overall_summary         JSONB NOT NULL DEFAULT '{}',
    detailed_explanation    JSONB NOT NULL DEFAULT '{}',
    limitations             TEXT[],
    ai_model                TEXT NOT NULL,
    prompt_version          TEXT NOT NULL DEFAULT '1.0',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(report_id)
);

-- ============================================================
-- TABLE: doctor_questions
-- Questions generated from report analysis
-- ============================================================
CREATE TABLE IF NOT EXISTS public.doctor_questions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id           UUID NOT NULL REFERENCES public.medical_reports(id) ON DELETE CASCADE,
    question            TEXT NOT NULL,
    question_order      INTEGER NOT NULL DEFAULT 0,
    discussion_status   TEXT NOT NULL DEFAULT 'PENDING'
                            CHECK (discussion_status IN ('PENDING', 'DISCUSSED')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: payments
-- Individual payment records from Razorpay
-- ============================================================
CREATE TABLE IF NOT EXISTS public.payments (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                 UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    subscription_id         UUID REFERENCES public.subscriptions(id) ON DELETE SET NULL,
    gateway_payment_id      TEXT UNIQUE NOT NULL,
    gateway_order_id        TEXT,
    amount                  INTEGER NOT NULL,   -- in paise
    currency                TEXT NOT NULL DEFAULT 'INR',
    payment_status          TEXT NOT NULL
                                CHECK (payment_status IN (
                                    'AUTHORIZED', 'CAPTURED', 'FAILED',
                                    'REFUNDED', 'PENDING'
                                )),
    payment_method          TEXT,
    payment_date            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: subscription_events
-- Raw webhook events — used for idempotency and audit
-- ============================================================
CREATE TABLE IF NOT EXISTS public.subscription_events (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subscription_id     UUID REFERENCES public.subscriptions(id) ON DELETE SET NULL,
    event_type          TEXT NOT NULL,
    gateway_event_id    TEXT UNIQUE NOT NULL,   -- Razorpay event ID, prevents duplicates
    payload             JSONB,
    event_status        TEXT NOT NULL DEFAULT 'PROCESSED'
                            CHECK (event_status IN ('PROCESSED', 'FAILED', 'DUPLICATE')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: notification_log
-- Prevents duplicate email notifications
-- ============================================================
CREATE TABLE IF NOT EXISTS public.notification_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL,  -- 'trial_reminder_7d', 'trial_expired', etc.
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, notification_type)
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_medical_reports_user_id       ON public.medical_reports(user_id);
CREATE INDEX IF NOT EXISTS idx_medical_reports_status        ON public.medical_reports(processing_status);
CREATE INDEX IF NOT EXISTS idx_extracted_parameters_report   ON public.extracted_parameters(report_id);
CREATE INDEX IF NOT EXISTS idx_report_analyses_report        ON public.report_analyses(report_id);
CREATE INDEX IF NOT EXISTS idx_doctor_questions_report       ON public.doctor_questions(report_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id         ON public.subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status          ON public.subscriptions(subscription_status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_gateway_id      ON public.subscriptions(gateway_subscription_id);
CREATE INDEX IF NOT EXISTS idx_payments_user_id              ON public.payments(user_id);
CREATE INDEX IF NOT EXISTS idx_subscription_events_gateway   ON public.subscription_events(gateway_event_id);
CREATE INDEX IF NOT EXISTS idx_notification_log_user         ON public.notification_log(user_id);

-- ============================================================
-- TRIGGER: auto-update updated_at timestamps
-- ============================================================
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_profiles_updated_at ON public.profiles;
CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_subscriptions_updated_at ON public.subscriptions;
CREATE TRIGGER trg_subscriptions_updated_at
    BEFORE UPDATE ON public.subscriptions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TRIGGER: auto-create profile + trial subscription on signup
-- ============================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    -- Create profile
    INSERT INTO public.profiles (id, email, display_name)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1))
    )
    ON CONFLICT (id) DO NOTHING;

    -- Create 30-day trial subscription
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

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Fire when user email is confirmed
DROP TRIGGER IF EXISTS trg_on_auth_user_created ON auth.users;
CREATE TRIGGER trg_on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================

-- Enable RLS on all tables
ALTER TABLE public.profiles              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.medical_reports       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.extracted_parameters  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.report_analyses       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.doctor_questions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payments              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscription_events   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_log      ENABLE ROW LEVEL SECURITY;

-- ── profiles ─────────────────────────────────────────────────
DROP POLICY IF EXISTS "Users read own profile" ON public.profiles;
CREATE POLICY "Users read own profile"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users update own profile" ON public.profiles;
CREATE POLICY "Users update own profile"
    ON public.profiles FOR UPDATE
    USING (auth.uid() = id);

-- Admins can read all profiles (for admin dashboard)
DROP POLICY IF EXISTS "Admins read all profiles" ON public.profiles;
CREATE POLICY "Admins read all profiles"
    ON public.profiles FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles p
            WHERE p.id = auth.uid() AND p.is_admin = TRUE
        )
    );

-- ── medical_reports ──────────────────────────────────────────
DROP POLICY IF EXISTS "Users manage own reports" ON public.medical_reports;
CREATE POLICY "Users manage own reports"
    ON public.medical_reports FOR ALL
    USING (auth.uid() = user_id);

-- ── extracted_parameters ─────────────────────────────────────
DROP POLICY IF EXISTS "Users read own parameters" ON public.extracted_parameters;
CREATE POLICY "Users read own parameters"
    ON public.extracted_parameters FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM public.medical_reports r
            WHERE r.id = report_id AND r.user_id = auth.uid()
        )
    );

-- ── report_analyses ──────────────────────────────────────────
DROP POLICY IF EXISTS "Users read own analyses" ON public.report_analyses;
CREATE POLICY "Users read own analyses"
    ON public.report_analyses FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM public.medical_reports r
            WHERE r.id = report_id AND r.user_id = auth.uid()
        )
    );

-- ── doctor_questions ─────────────────────────────────────────
DROP POLICY IF EXISTS "Users manage own questions" ON public.doctor_questions;
CREATE POLICY "Users manage own questions"
    ON public.doctor_questions FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM public.medical_reports r
            WHERE r.id = report_id AND r.user_id = auth.uid()
        )
    );

-- ── subscriptions ────────────────────────────────────────────
DROP POLICY IF EXISTS "Users read own subscription" ON public.subscriptions;
CREATE POLICY "Users read own subscription"
    ON public.subscriptions FOR SELECT
    USING (auth.uid() = user_id);

-- ── payments ─────────────────────────────────────────────────
DROP POLICY IF EXISTS "Users read own payments" ON public.payments;
CREATE POLICY "Users read own payments"
    ON public.payments FOR SELECT
    USING (auth.uid() = user_id);

-- ── subscription_events ──────────────────────────────────────
DROP POLICY IF EXISTS "No direct user access to events" ON public.subscription_events;
CREATE POLICY "No direct user access to events"
    ON public.subscription_events FOR ALL
    USING (FALSE);

-- ── notification_log ─────────────────────────────────────────
DROP POLICY IF EXISTS "No direct user access to notification log" ON public.notification_log;
CREATE POLICY "No direct user access to notification log"
    ON public.notification_log FOR ALL
    USING (FALSE);

-- ============================================================
-- STORAGE BUCKET & RLS POLICIES (medical-reports)
-- Private bucket: files accessible only via signed URLs or owner
-- ============================================================

-- Ensure the private bucket exists
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'medical-reports',
    'medical-reports',
    FALSE,
    20971520, -- 20MB in bytes
    ARRAY['application/pdf', 'image/jpeg', 'image/jpg', 'image/png']
)
ON CONFLICT (id) DO UPDATE SET
    public = FALSE,
    file_size_limit = 20971520,
    allowed_mime_types = ARRAY['application/pdf', 'image/jpeg', 'image/jpg', 'image/png'];

-- Note: Row Level Security is already enabled on storage.objects by default in all Supabase projects.
-- (The table is owned by supabase_storage_admin; ALTER TABLE is omitted to avoid 42501 ownership error).

-- Storage RLS: Users can only upload into their own folder: {user_id}/*
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Users upload own reports'
    ) THEN
        CREATE POLICY "Users upload own reports"
            ON storage.objects FOR INSERT
            WITH CHECK (
                bucket_id = 'medical-reports'
                AND auth.uid()::TEXT = (storage.foldername(name))[1]
            );
    END IF;
END $$;

-- Storage RLS: Users can only read from their own folder
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Users read own reports'
    ) THEN
        CREATE POLICY "Users read own reports"
            ON storage.objects FOR SELECT
            USING (
                bucket_id = 'medical-reports'
                AND auth.uid()::TEXT = (storage.foldername(name))[1]
            );
    END IF;
END $$;

-- Storage RLS: Users can delete their own files
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Users delete own reports'
    ) THEN
        CREATE POLICY "Users delete own reports"
            ON storage.objects FOR DELETE
            USING (
                bucket_id = 'medical-reports'
                AND auth.uid()::TEXT = (storage.foldername(name))[1]
            );
    END IF;
END $$;


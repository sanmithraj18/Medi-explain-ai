# MediExplain AI — Production Architecture & Deployment Guide

## 1. System Overview

MediExplain AI is a production-oriented medical report explanation SaaS built with:
- **Frontend:** Next.js 14 App Router, TypeScript, Tailwind CSS, shadcn/ui, Sonner
- **Backend:** FastAPI, Pydantic, SlowAPI rate-limiting, PyMuPDF, Tesseract OCR
- **Database & Storage:** Supabase PostgreSQL with Row Level Security (RLS) & private encrypted storage
- **AI Processing:** Google Gemini 1.5 Flash with structured JSON output and clinical safety guardrails
- **Billing & Subscriptions:** Razorpay Subscriptions API with 30-day trial and ₹200/month recurring mandate

---

## 2. Supabase Setup (Database & Private Storage)

1. Create a new Supabase project at [https://supabase.com](https://supabase.com).
2. Open the **SQL Editor** in the Supabase Dashboard.
3. Paste and run the entire contents of `supabase/migrations/001_initial_schema.sql`.
4. Create the private storage bucket:
   - Navigate to **Storage** in the Supabase dashboard.
   - Click **Create Bucket**.
   - Name: `medical-reports`
   - **Public bucket:** OFF (Disabled)
5. Copy your API credentials:
   - Go to **Project Settings** > **API**.
   - Copy **Project URL** -> `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL`
   - Copy **anon public** -> `SUPABASE_ANON_KEY` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - Copy **service_role secret** -> `SUPABASE_SERVICE_ROLE_KEY` (Backend only!)

---

## 3. Razorpay Subscription Configuration (Test Mode)

1. Sign in to your [Razorpay Dashboard](https://dashboard.razorpay.com).
2. Ensure you are in **Test Mode**.
3. Generate API Keys in **Settings > API Keys**:
   - `RAZORPAY_KEY_ID` (Public key: starts with `rzp_test_`)
   - `RAZORPAY_KEY_SECRET` (Secret key: backend only!)
4. Configure Webhook in **Settings > Webhooks**:
   - URL: `https://your-backend-domain.com/api/v1/payments/razorpay/webhook`
   - Secret: Generate a secret key and set as `RAZORPAY_WEBHOOK_SECRET`
   - Select Events:
     - `subscription.activated`
     - `subscription.charged`
     - `subscription.halted`
     - `subscription.cancelled`
     - `payment.captured`
     - `payment.failed`

---

## 4. Google Gemini AI Setup

1. Obtain an API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Add to backend `.env`:
   ```bash
   AI_API_KEY=your_gemini_api_key
   AI_MODEL=gemini-1.5-flash
   ```

---

## 5. Deployment Instructions

### Frontend (Vercel)
1. Push your repository to GitHub / GitLab.
2. Import the project into Vercel.
3. Set the Root Directory to `frontend`.
4. Add the environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_BACKEND_API_URL`
   - `NEXT_PUBLIC_RAZORPAY_KEY_ID`
5. Deploy.

### Backend (Railway / Render / Cloud Run)
1. Set the Root Directory to `backend`.
2. Ensure Tesseract OCR is available in your container or base image.
3. Start command: `uvicorn main:app --host 0.0.0.0 --port 8000`
4. Configure all secret environment variables from `backend/.env.example`.
5. Deploy.


# MediExplain AI

> **"Your Reports. Simplified. Your Health Conversations. Empowered."**

A complete, production-oriented healthcare SaaS platform engineered to help patients understand complex laboratory reports, review clear parameter explanations, and prepare doctor discussion questions.

---

## 🌟 Key Features

1. **Premium Responsive UI & Landing Page**
   - Brand aesthetic: Deep navy blue (`#0f172a`), teal (`#0d9488`), and soft blue-grey
   - 11 comprehensive landing sections: Hero, Features, How it works, Sample Fictional Report, Privacy & Security, Pricing, FAQs, and Medical Disclaimers.

2. **Secure Authentication & Ownership Isolation**
   - Supabase Auth (Email/Password & Google OAuth)
   - Database Row Level Security (RLS) guaranteeing that no user can access another user's reports
   - Private Supabase Storage bucket (`medical-reports`) accessed only via short-lived signed URLs

3. **Multi-Format Upload & Camera Scanning**
   - Drag & drop PDF, JPG, and PNG uploads up to 20MB
   - Direct device camera scanning for physical paperwork
   - Magic bytes and MIME verification to prevent malicious file uploads

4. **Document Processing & OCR Extraction Pipeline**
   - Native PDF text extraction using PyMuPDF (`pymupdf`)
   - Scanned page & camera photo OCR using Tesseract 5
   - Intelligent parameter parser extracting Test Name, Measured Value, Unit, Reference Interval, and High/Low Flags without hallucinating data

5. **AI Clinical Explanation with Safety Guardrails**
   - Google Gemini 1.5 Flash structured JSON integration
   - Strict medical safety prompt engineering:
     - ❌ No disease diagnoses
     - ❌ No medication prescriptions or dosage changes
     - ❌ No invented laboratory numbers or reference ranges
     - ❌ No false reassurance
     - ✅ Explicit distinction between out-of-range lab markers and confirmed diseases
     - ✅ Informational disclaimers on all outputs

6. **Doctor Discussion Guide Generator**
   - Personalized discussion questions based on extracted lab results
   - One-click copy, status tracking ("Mark Discussed"), and PDF printing

7. **30-Day Free Trial & ₹200/Month Recurring Subscriptions**
   - Exactly 30 calendar days trial starting from email verification
   - Real-time countdown banner in user dashboard
   - Razorpay Subscriptions API integration with explicit recurring-payment mandate consent
   - HMAC-SHA256 signature verification for checkouts and webhooks
   - Self-serve cancellation preventing future charges

8. **Admin Telemetry Dashboard**
   - Role-based server-side protection (`is_admin = TRUE`)
   - Verified revenue calculations based only on captured payments (free trials never counted as revenue)
   - Zero patient medical data exposure in admin consoles

---

## 🛠️ Project Structure

```
Medi-explain-ai/
├── frontend/                    # Next.js 14 App Router, TypeScript, Tailwind CSS
│   ├── src/app/
│   │   ├── (auth)/              # Login, register, forgot-password, verify-email
│   │   ├── dashboard/           # Overview, upload, reports history, billing
│   │   ├── dashboard/report/[id]# Detailed report analysis & doctor questions
│   │   ├── admin/               # Administrator telemetry dashboard
│   │   ├── terms/, privacy/, refund/
│   │   └── page.tsx             # Complete 11-section landing page
│   └── src/lib/                 # Supabase client, utils, API client
│
├── backend/                     # FastAPI REST API, PyMuPDF, Tesseract, Gemini
│   ├── app/api/v1/endpoints/   # Reports, analysis, subscriptions, webhooks, admin
│   ├── app/core/                # Security, dependencies, config (pydantic-settings)
│   ├── app/services/ocr/        # PDF extraction, image OCR, regex parser
│   ├── app/services/ai/         # Gemini structured explanation service
│   ├── app/services/payment/    # Razorpay SDK client & signature verifier
│   ├── tests/                   # Pytest test suite
│   ├── requirements.txt         # Production Python dependencies
│   └── main.py                  # ASGI entry point
│
├── supabase/migrations/         # PostgreSQL DDL migrations & RLS policies
│   └── 001_initial_schema.sql
├── docs/                        # Deployment & REST API specifications
│   ├── DEPLOYMENT.md
│   └── API.md
└── .env.example                 # Unified configuration template
```

---

## 🚀 Getting Started Locally

### 1. Database & Migrations
1. Create a Supabase project at [supabase.com](https://supabase.com).
2. Run `supabase/migrations/001_initial_schema.sql` in the Supabase SQL Editor.
3. Create a private bucket named `medical-reports` in Supabase Storage.

### 2. Backend Setup
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env # Add your credentials
uvicorn main:app --reload --port 8000
```

Run backend tests:
```bash
pytest -v
```

### 3. Frontend Setup
```bash
cd frontend
npm install
cp .env.example .env.local # Add your public keys
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the application.

---

## 🔒 Security & Privacy Notice

MediExplain AI is designed with strict healthcare data confidentiality principles:
- Reports are stored in private encrypted storage.
- Database records are protected by PostgreSQL Row Level Security (RLS).
- No medical data is displayed without user authentication.
- Medical disclaimers are present on all explanations and landing pages.

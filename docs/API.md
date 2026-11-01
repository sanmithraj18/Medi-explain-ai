# MediExplain AI — Backend REST API Specification

Base URL: `/api/v1`

---

## 1. Authentication & Profiles (`/auth`)

### `GET /auth/me`
- **Auth:** Bearer Supabase JWT
- **Description:** Returns the authenticated user profile.

### `PATCH /auth/me`
- **Auth:** Bearer Supabase JWT
- **Body:** `{ "display_name": "string" }`
- **Description:** Updates the display name of the user.

---

## 2. Medical Reports (`/reports`)

### `POST /reports/upload`
- **Auth:** Bearer Supabase JWT (Requires active trial or subscription)
- **Content-Type:** `multipart/form-data`
- **Fields:**
  - `file`: PDF, JPG, or PNG (up to 20MB)
  - `report_name` (optional): string
- **Returns:** `{ "report_id": "uuid", "parameters_found": 5, "processing_status": "EXTRACTED" }`

### `GET /reports/`
- **Auth:** Bearer Supabase JWT
- **Returns:** List of user's uploaded reports.

### `GET /reports/{id}`
- **Auth:** Bearer Supabase JWT
- **Returns:** Metadata for a single report.

### `GET /reports/{id}/parameters`
- **Auth:** Bearer Supabase JWT
- **Returns:** Extracted parameter rows with observed values, units, reference intervals, and flags.

### `GET /reports/{id}/download-url`
- **Auth:** Bearer Supabase JWT
- **Returns:** 60-minute short-lived signed URL for the document.

### `DELETE /reports/{id}`
- **Auth:** Bearer Supabase JWT
- **Returns:** Deletes report record and purged cloud storage file.

---

## 3. AI Analysis (`/analysis`)

### `POST /analysis/{report_id}/trigger`
- **Auth:** Bearer Supabase JWT (Requires active trial or subscription)
- **Description:** Sends extracted parameters to Gemini with medical safety guardrails.
- **Returns:** Structured JSON summary, parameter explanations, and doctor questions.

### `GET /analysis/{report_id}`
- **Auth:** Bearer Supabase JWT
- **Returns:** Stored AI explanation for the report.

---

## 4. Doctor Discussion Questions (`/questions`)

### `GET /questions/report/{report_id}`
- **Auth:** Bearer Supabase JWT
- **Returns:** Tailored questions generated from test findings.

### `PATCH /questions/{id}/status`
- **Auth:** Bearer Supabase JWT
- **Body:** `{ "discussion_status": "DISCUSSED" | "PENDING" }`

---

## 5. Subscriptions & Billing (`/subscriptions`)

### `GET /subscriptions/me`
- **Auth:** Bearer Supabase JWT
- **Returns:** Subscription record with computed `trial_days_remaining`.

### `POST /subscriptions/create-checkout`
- **Auth:** Bearer Supabase JWT
- **Description:** Initializes a recurring subscription in Razorpay (30-day trial offset).
- **Returns:** Gateway subscription ID and public Razorpay Key ID for checkout modal.

### `POST /subscriptions/verify-checkout`
- **Auth:** Bearer Supabase JWT
- **Body:** `{ "razorpay_payment_id": "...", "razorpay_subscription_id": "...", "razorpay_signature": "..." }`
- **Description:** Verifies payment signature server-side using HMAC-SHA256.

### `POST /subscriptions/cancel`
- **Auth:** Bearer Supabase JWT
- **Description:** Cancels subscription at cycle end or immediately during trial.

---

## 6. Payments & Webhooks (`/payments`)

### `POST /payments/razorpay/webhook`
- **Auth:** Signature verified via `X-Razorpay-Signature` header
- **Events:**
  - `subscription.activated`
  - `subscription.charged`
  - `subscription.halted`
  - `subscription.cancelled`
  - `payment.captured`
  - `payment.failed`
- **Idempotency:** Guarded by `subscription_events.gateway_event_id` unique constraint.

---

## 7. Admin Metrics (`/admin`)

### `GET /admin/stats`
- **Auth:** Bearer Supabase JWT (Requires `is_admin = TRUE` in `profiles` table)
- **Returns:** Aggregate user counts, subscription breakdowns, verified revenue in INR, and document counts.
- **Privacy:** Medical report contents are strictly excluded.


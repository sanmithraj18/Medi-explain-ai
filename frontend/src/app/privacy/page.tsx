import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen bg-surface py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto space-y-8 bg-white p-8 sm:p-12 rounded-2xl border border-slate-100 shadow-card">
        <div>
          <Link href="/" className="inline-flex items-center gap-1.5 text-xs font-semibold text-teal hover:underline mb-4">
            <ArrowLeft size={14} /> Back to MediExplain AI
          </Link>
          <h1 className="text-3xl font-bold text-navy">Privacy Policy</h1>
          <p className="text-xs text-blue-grey mt-1">Last Updated: November 2026</p>
        </div>

        <div className="prose prose-slate text-xs sm:text-sm leading-relaxed space-y-4 text-slate-700">
          <h2 className="text-base font-bold text-navy">1. Information We Collect</h2>
          <p>
            When you register for MediExplain AI, we collect your email address, full name, and authentication tokens. When you upload medical documents (PDFs, JPGs, PNGs), they are stored in private cloud storage protected by PostgreSQL Row Level Security (RLS).
          </p>

          <h2 className="text-base font-bold text-navy">2. How Medical Data is Handled</h2>
          <p>
            Medical documents are parsed through on-premise/server-side OCR (PyMuPDF and Tesseract OCR). Only structured numeric laboratory parameters (test names, observed values, units, and reference intervals) are transmitted to the AI engine to generate plain-language explanations. Identifiable patient metadata is segregated.
          </p>

          <h2 className="text-base font-bold text-navy">3. Row Level Security & Encryption</h2>
          <p>
            All user data is encrypted in transit via TLS 1.3 and at rest with 256-bit encryption. Supabase Row Level Security strictly ensures that no user can view or query another user&apos;s reports under any circumstances.
          </p>

          <h2 className="text-base font-bold text-navy">4. Payment Information</h2>
          <p>
            Payment transactions and recurring mandates are processed directly by Razorpay, a PCI-DSS certified payment gateway. MediExplain AI never receives or stores your full credit card number, debit card number, CVV, or UPI PIN.
          </p>

          <h2 className="text-base font-bold text-navy">5. Deletion & Data Retention</h2>
          <p>
            You may permanently delete any uploaded medical report at any time from your Report History dashboard. Deleting a report immediately purges the file from cloud storage and removes all associated extracted parameters and analyses.
          </p>
        </div>
      </div>
    </div>
  );
}


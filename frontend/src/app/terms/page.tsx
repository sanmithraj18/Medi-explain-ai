import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

export default function TermsOfServicePage() {
  return (
    <div className="min-h-screen bg-surface py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto space-y-8 bg-white p-8 sm:p-12 rounded-2xl border border-slate-100 shadow-card">
        <div>
          <Link href="/" className="inline-flex items-center gap-1.5 text-xs font-semibold text-teal hover:underline mb-4">
            <ArrowLeft size={14} /> Back to MediExplain AI
          </Link>
          <h1 className="text-3xl font-bold text-navy">Terms of Service</h1>
          <p className="text-xs text-blue-grey mt-1">Last Updated: November 2026</p>
        </div>

        <div className="prose prose-slate text-xs sm:text-sm leading-relaxed space-y-4 text-slate-700">
          <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-amber-900 font-medium">
            <strong>CRITICAL MEDICAL DISCLAIMER:</strong> MediExplain AI is an automated software tool providing informational insights regarding laboratory test results. MediExplain AI is not a medical device, is not operated by medical professionals, does not provide medical diagnoses, and is not a substitute for professional clinical advice. Always consult a licensed healthcare practitioner.
          </div>

          <h2 className="text-base font-bold text-navy">1. Acceptance of Terms</h2>
          <p>
            By creating an account, uploading documents, or subscribing to MediExplain AI (&quot;Service&quot;), you agree to be bound by these Terms of Service. If you disagree with any part of these terms, you must not use our Service.
          </p>

          <h2 className="text-base font-bold text-navy">2. Free Trial & 30-Day Evaluation</h2>
          <p>
            Eligible registered users receive a free trial lasting exactly 30 calendar days from the date of account verification. No payment is debited during this period. At the end of the trial period, access to premium AI analysis requires authorization of an active subscription.
          </p>

          <h2 className="text-base font-bold text-navy">3. Monthly Recurring Billing (₹200 / Month)</h2>
          <p>
            Upon authorizing the recurring subscription, you consent to automatic monthly recurring debits of ₹200 (INR) via Razorpay. Subscriptions renew automatically every 30 days until cancelled by the user. Mandate authorization occurs according to Reserve Bank of India (RBI) e-mandate regulations.
          </p>

          <h2 className="text-base font-bold text-navy">4. Cancellation & Termination</h2>
          <p>
            You may cancel your subscription at any time directly through the Billing Dashboard. Cancellation takes effect at the end of the current billing cycle or immediately if cancelled during the trial period. No subsequent charges will be made following confirmed cancellation.
          </p>

          <h2 className="text-base font-bold text-navy">5. Medical Data & Intellectual Property</h2>
          <p>
            You retain all rights and ownership to the medical reports you upload. You grant MediExplain AI a limited license solely to process and extract text from your documents to deliver the service. We do not sell or share your medical data.
          </p>
        </div>
      </div>
    </div>
  );
}

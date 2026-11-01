import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

export default function RefundPolicyPage() {
  return (
    <div className="min-h-screen bg-surface py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto space-y-8 bg-white p-8 sm:p-12 rounded-2xl border border-slate-100 shadow-card">
        <div>
          <Link href="/" className="inline-flex items-center gap-1.5 text-xs font-semibold text-teal hover:underline mb-4">
            <ArrowLeft size={14} /> Back to MediExplain AI
          </Link>
          <h1 className="text-3xl font-bold text-navy">Refund & Cancellation Policy</h1>
          <p className="text-xs text-blue-grey mt-1">Last Updated: November 2026</p>
        </div>

        <div className="prose prose-slate text-xs sm:text-sm leading-relaxed space-y-4 text-slate-700">
          <h2 className="text-base font-bold text-navy">1. 30-Day Zero-Risk Free Trial</h2>
          <p>
            MediExplain AI provides a full 30-day free trial on initial account registration. No payments are charged during this period. You are free to cancel your recurring mandate authorization at any point before the 30 days elapse with zero debits.
          </p>

          <h2 className="text-base font-bold text-navy">2. Monthly Recurring Charges (₹200 / Month)</h2>
          <p>
            Once the trial expires and a recurring mandate has been authorized, ₹200 (INR) is debited at each monthly billing cycle. You may cancel renewal at any time via the Billing dashboard.
          </p>

          <h2 className="text-base font-bold text-navy">3. Refund Requests</h2>
          <p>
            If you experience an accidental charge or technical failure where report analysis was completely inaccessible despite an active subscription, you may request a refund within 7 calendar days of the charge date by emailing support@mediexplain.ai.
          </p>

          <h2 className="text-base font-bold text-navy">4. Refund Processing</h2>
          <p>
            Approved refunds will be credited back to the original payment source (bank account, UPI, or card) within 5 to 7 business days in accordance with standard banking and Razorpay turnaround times.
          </p>
        </div>
      </div>
    </div>
  );
}


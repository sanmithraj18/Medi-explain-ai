'use client';

import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Activity, MailCheck, ArrowRight, ShieldCheck } from 'lucide-react';
import { Suspense } from 'react';

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const email = searchParams.get('email') || 'your email';

  return (
    <div className="bg-white py-8 px-6 shadow-card rounded-2xl sm:px-10 border border-slate-100 text-center">
      <div className="w-16 h-16 bg-teal/10 rounded-2xl flex items-center justify-center mx-auto mb-5 text-teal">
        <MailCheck size={32} />
      </div>

      <h2 className="text-2xl font-bold tracking-tight text-navy mb-2">
        Verify your email
      </h2>

      <p className="text-sm text-blue-grey leading-relaxed mb-6">
        We sent a verification link to <span className="font-semibold text-navy">{email}</span>. Click the link in the message to activate your 30-day free trial.
      </p>

      <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-left mb-6 space-y-2 text-xs text-blue-grey">
        <div className="flex items-center gap-2 text-navy font-semibold">
          <ShieldCheck size={16} className="text-teal" /> What happens next:
        </div>
        <p>1. Open the email sent from MediExplain AI.</p>
        <p>2. Click &quot;Confirm your mail&quot; to verify your identity.</p>
        <p>3. Your 30-day trial activates instantly with complete access to report analysis.</p>
      </div>

      <Link href="/login" className="btn-primary justify-center w-full text-sm py-2.5">
        Go to Sign In <ArrowRight size={16} />
      </Link>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <div className="min-h-screen bg-surface flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center mb-6">
        <Link href="/" className="inline-flex items-center gap-2.5">
          <div className="w-10 h-10 bg-gradient-to-br from-teal to-navy rounded-xl flex items-center justify-center shadow-md">
            <Activity className="text-white" size={22} />
          </div>
          <span className="font-bold text-2xl text-navy">
            MediExplain <span className="text-teal">AI</span>
          </span>
        </Link>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md px-4 sm:px-0">
        <Suspense fallback={<div className="text-center p-8 text-blue-grey">Loading...</div>}>
          <VerifyEmailContent />
        </Suspense>
      </div>
    </div>
  );
}


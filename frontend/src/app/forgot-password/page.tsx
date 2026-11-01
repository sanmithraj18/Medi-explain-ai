'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Activity, Mail, ArrowRight, ArrowLeft, CheckCircle2, AlertCircle } from 'lucide-react';
import { createClient } from '@/lib/supabase/client';
import { toast } from 'sonner';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setLoading(true);

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/login?reset=true`,
      });

      if (error) {
        setErrorMsg(error.message);
        toast.error(error.message);
        return;
      }

      setSubmitted(true);
      toast.success('Password reset instructions sent!');
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to send password reset email.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <Link href="/" className="inline-flex items-center gap-2.5">
          <div className="w-10 h-10 bg-gradient-to-br from-teal to-navy rounded-xl flex items-center justify-center shadow-md">
            <Activity className="text-white" size={22} />
          </div>
          <span className="font-bold text-2xl text-navy">
            MediExplain <span className="text-teal">AI</span>
          </span>
        </Link>
        <h2 className="mt-6 text-2xl font-bold tracking-tight text-navy">
          Reset your password
        </h2>
        <p className="mt-2 text-sm text-blue-grey">
          Enter your registered email address to receive password recovery instructions.
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md px-4 sm:px-0">
        <div className="bg-white py-8 px-6 shadow-card rounded-2xl sm:px-10 border border-slate-100">
          {submitted ? (
            <div className="text-center py-4">
              <div className="w-12 h-12 bg-teal/10 rounded-full flex items-center justify-center mx-auto mb-4 text-teal">
                <CheckCircle2 size={28} />
              </div>
              <h3 className="text-lg font-bold text-navy mb-2">Check your email</h3>
              <p className="text-sm text-blue-grey mb-6 leading-relaxed">
                If an account exists for <span className="font-semibold text-navy">{email}</span>, we have sent a secure password reset link.
              </p>
              <Link
                href="/login"
                className="btn-outline justify-center w-full text-sm py-2.5"
              >
                <ArrowLeft size={16} /> Return to sign in
              </Link>
            </div>
          ) : (
            <form className="space-y-5" onSubmit={handleReset}>
              {errorMsg && (
                <div className="p-4 rounded-xl bg-red-50 border border-red-200 flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
                  <p className="text-sm text-red-700">{errorMsg}</p>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-navy">Email address</label>
                <div className="mt-1.5 relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                    <Mail size={18} />
                  </div>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="block w-full pl-10 pr-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm text-navy placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal focus:border-transparent transition"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full btn-primary justify-center py-2.5 text-sm disabled:opacity-50"
              >
                {loading ? 'Sending link...' : 'Send Reset Link'}
                {!loading && <ArrowRight size={16} />}
              </button>

              <div className="text-center pt-2">
                <Link
                  href="/login"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-grey hover:text-navy"
                >
                  <ArrowLeft size={14} /> Back to sign in
                </Link>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}


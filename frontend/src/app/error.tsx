'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log the error for debugging — never expose stack traces to users
    console.error('[MediExplain AI] Client-side exception:', error?.message, error?.digest);
  }, [error]);

  return (
    <div className="min-h-screen bg-surface flex flex-col items-center justify-center px-4 py-16">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-8 max-w-md w-full text-center space-y-5">
        <div className="w-16 h-16 rounded-2xl bg-red-50 text-red-500 flex items-center justify-center mx-auto">
          <AlertTriangle size={32} />
        </div>

        <div>
          <h1 className="text-xl font-bold text-navy mb-2">Something went wrong</h1>
          <p className="text-sm text-blue-grey leading-relaxed">
            An unexpected error occurred. Your data is safe — please try refreshing the page or
            returning to the dashboard.
          </p>
          {error?.digest && (
            <p className="text-xs text-slate-400 mt-2 font-mono">
              Error ID: {error.digest}
            </p>
          )}
        </div>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <button
            onClick={reset}
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-teal text-white font-semibold text-sm rounded-xl hover:bg-teal-dark transition"
          >
            <RefreshCw size={16} />
            Try Again
          </button>
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 border border-slate-200 text-navy font-semibold text-sm rounded-xl hover:bg-slate-50 transition"
          >
            <Home size={16} />
            Go to Dashboard
          </Link>
        </div>

        <p className="text-xs text-slate-400 pt-2 border-t border-slate-100">
          If this problem persists, please try signing out and signing back in.
        </p>
      </div>
    </div>
  );
}

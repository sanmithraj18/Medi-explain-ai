'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[MediExplain Dashboard] Runtime error:', error?.message, error?.digest);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4 text-center space-y-5">
      <div className="w-14 h-14 rounded-2xl bg-red-50 text-red-500 flex items-center justify-center">
        <AlertTriangle size={28} />
      </div>

      <div>
        <h2 className="text-lg font-bold text-navy mb-2">Page failed to load</h2>
        <p className="text-sm text-blue-grey max-w-sm mx-auto leading-relaxed">
          An error occurred while loading this page. Your data is safe. Try refreshing or navigate
          back to the dashboard overview.
        </p>
        {error?.digest && (
          <p className="text-xs text-slate-400 mt-2 font-mono">Error ID: {error.digest}</p>
        )}
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <button
          onClick={reset}
          className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-teal text-white font-semibold text-sm rounded-xl hover:bg-teal-dark transition"
        >
          <RefreshCw size={16} />
          Retry
        </button>
        <Link
          href="/dashboard"
          className="inline-flex items-center justify-center gap-2 px-4 py-2.5 border border-slate-200 text-navy font-semibold text-sm rounded-xl hover:bg-slate-50 transition"
        >
          <Home size={16} />
          Dashboard Home
        </Link>
      </div>
    </div>
  );
}


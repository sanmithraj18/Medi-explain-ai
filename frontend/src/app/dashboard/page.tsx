'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { 
  Upload, FileText, AlertTriangle, ArrowRight, 
  Sparkles, ShieldCheck, ChevronRight, Activity, Calendar,
  CheckCircle2, Clock, RefreshCw
} from 'lucide-react';
import { createClient } from '@/lib/supabase/client';
import { formatDate, daysUntil } from '@/lib/utils';

export default function DashboardOverviewPage() {
  const [subscription, setSubscription] = useState<any>(null);
  const [reports, setReports] = useState<any[]>([]);
  const [stats, setStats] = useState<{
    total_reports: number;
    completed_explanations: number;
    needs_review: number;
    processing: number;
  }>({
    total_reports: 0,
    completed_explanations: 0,
    needs_review: 0,
    processing: 0,
  });
  const [loading, setLoading] = useState(true);

  const backendUrl = (process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

  const loadData = useCallback(async () => {
    try {
      const supabase = createClient();
      const { data: { user } } = await supabase.auth.getUser();

      if (user) {
        const { data: { session } } = await supabase.auth.getSession();
        const headers: Record<string, string> = {};
        if (session?.access_token) {
          headers['Authorization'] = `Bearer ${session.access_token}`;
        }

        // 1. Fetch subscription from backend (server-side evaluated)
        try {
          const subRes = await fetch(`${backendUrl}/api/v1/subscriptions/current`, { headers });
          if (subRes.ok) {
            const liveSub = await subRes.json();
            setSubscription(liveSub);
          } else {
            const { data: subData } = await supabase
              .from('subscriptions')
              .select('*')
              .eq('user_id', user.id)
              .maybeSingle();
            if (subData) setSubscription(subData);
          }
        } catch {
          const { data: subData } = await supabase
            .from('subscriptions')
            .select('*')
            .eq('user_id', user.id)
            .maybeSingle();
          if (subData) setSubscription(subData);
        }

        // 2. Fetch stats from backend
        try {
          const statsRes = await fetch(`${backendUrl}/api/v1/reports/stats`, { headers });
          if (statsRes.ok) {
            const statsData = await statsRes.json();
            setStats(statsData);
          }
        } catch {
          // Fallback if backend unreachable
        }

        // 3. Fetch recent reports
        const { data: reportsData } = await supabase
          .from('medical_reports')
          .select('*')
          .eq('user_id', user.id)
          .order('created_at', { ascending: false })
          .limit(5);

        if (reportsData) {
          setReports(reportsData);
        }
      }
    } catch (err) {
      console.error('Error fetching dashboard data:', err);
    } finally {
      setLoading(false);
    }
  }, [backendUrl]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const trialDaysRemaining = subscription?.trial_end_date 
    ? Math.max(0, daysUntil(subscription.trial_end_date) ?? 0)
    : 30;

  const isTrialActive = subscription?.subscription_status === 'TRIAL_ACTIVE' || !subscription;

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Welcome Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-navy">
            Clinical Health Workspace
          </h1>
          <p className="text-sm text-blue-grey mt-1">
            Secure, patient-friendly medical report explanation and lab parameter tracking.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link href="/dashboard/upload" className="btn-primary text-xs !py-2.5 !px-4 shadow-sm inline-flex items-center gap-2">
            <Upload size={15} /> Upload Report
          </Link>
          <Link href="/dashboard/reports" className="btn-outline text-xs !py-2.5 !px-4 inline-flex items-center gap-2">
            <FileText size={15} /> Report History
          </Link>
        </div>
      </div>

      {/* Free Trial Countdown Banner */}
      {isTrialActive && (
        <div className="bg-gradient-to-r from-navy via-[#1e3a5f] to-teal-dark rounded-2xl p-6 text-white shadow-card relative overflow-hidden">
          <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-[radial-gradient(circle_at_center,rgba(20,184,166,0.25)_0,transparent_70%)] pointer-events-none" />
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 relative z-10">
            <div className="space-y-1.5">
              <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-white/10 rounded-full text-xs font-semibold text-teal-light backdrop-blur-xs">
                <Sparkles size={14} /> 30-Day Free Trial
              </div>
              <h2 className="text-xl sm:text-2xl font-bold">
                Your MediExplain AI free trial ends in{' '}
                <span className="text-teal-light underline decoration-2 underline-offset-4 font-extrabold">
                  {trialDaysRemaining} days
                </span>.
              </h2>
              <p className="text-xs sm:text-sm text-slate-300 max-w-xl leading-relaxed">
                Enjoy complete access to OCR report extraction, AI clinical explanations, and doctor discussion question generation. Continued access will be ₹200/month after your trial.
              </p>
            </div>
            <Link
              href="/dashboard/billing"
              className="inline-flex items-center gap-2 bg-teal hover:bg-teal-light text-navy font-bold px-5 py-2.5 rounded-xl text-sm transition shadow-md shrink-0"
            >
              Subscription Details <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      )}

      {/* Healthcare Metrics Row (4 Cards) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5">
        {/* Total Reports */}
        <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-card flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-blue-grey">Total Uploaded</span>
            <div className="w-8 h-8 rounded-lg bg-teal/10 text-teal flex items-center justify-center">
              <FileText size={16} />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-extrabold text-navy">
              {loading ? '-' : stats.total_reports}
            </div>
            <span className="text-[11px] text-blue-grey mt-0.5 block">Medical documents</span>
          </div>
        </div>

        {/* Completed Explanations */}
        <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-card flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-blue-grey">AI Explained</span>
            <div className="w-8 h-8 rounded-lg bg-green-100 text-green-700 flex items-center justify-center">
              <CheckCircle2 size={16} />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-extrabold text-navy">
              {loading ? '-' : stats.completed_explanations}
            </div>
            <span className="text-[11px] text-green-700 font-medium mt-0.5 block">Ready for clinical review</span>
          </div>
        </div>

        {/* Needs Verification */}
        <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-card flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-blue-grey">Awaiting Review</span>
            <div className="w-8 h-8 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center">
              <Clock size={16} />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-extrabold text-navy">
              {loading ? '-' : stats.needs_review}
            </div>
            <span className="text-[11px] text-amber-700 font-medium mt-0.5 block">Unconfirmed OCR values</span>
          </div>
        </div>

        {/* Trial Days Remaining */}
        <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-card flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-blue-grey">Trial Access</span>
            <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
              <Sparkles size={16} />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-extrabold text-navy">
              {trialDaysRemaining}d
            </div>
            <span className="text-[11px] text-teal-dark font-semibold mt-0.5 block">
              {isTrialActive ? 'Free Trial Active' : 'Active Plan'}
            </span>
          </div>
        </div>
      </div>

      {/* Quick Action Navigation Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
        <Link
          href="/dashboard/upload"
          className="bg-white p-6 rounded-2xl border border-slate-100 shadow-card hover:shadow-card-hover hover:border-teal/30 transition group flex flex-col justify-between"
        >
          <div>
            <div className="w-12 h-12 rounded-xl bg-teal/10 text-teal flex items-center justify-center mb-4 group-hover:scale-105 transition">
              <Upload size={22} />
            </div>
            <h3 className="font-bold text-navy text-base mb-1">Upload New Report</h3>
            <p className="text-xs text-blue-grey leading-relaxed">
              Scan or upload PDF, JPG, or PNG files for instant OCR extraction and patient-friendly explanations.
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-50 flex items-center text-xs font-semibold text-teal gap-1">
            Upload document <ChevronRight size={14} />
          </div>
        </Link>

        <Link
          href="/dashboard/reports"
          className="bg-white p-6 rounded-2xl border border-slate-100 shadow-card hover:shadow-card-hover hover:border-teal/30 transition group flex flex-col justify-between"
        >
          <div>
            <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center mb-4 group-hover:scale-105 transition">
              <FileText size={22} />
            </div>
            <h3 className="font-bold text-navy text-base mb-1">Report History</h3>
            <p className="text-xs text-blue-grey leading-relaxed">
              Search, filter, and review all your past reports, extracted parameter trends, and doctor notes.
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-50 flex items-center text-xs font-semibold text-blue-600 gap-1">
            View history <ChevronRight size={14} />
          </div>
        </Link>

        <Link
          href="/dashboard/billing"
          className="bg-white p-6 rounded-2xl border border-slate-100 shadow-card hover:shadow-card-hover hover:border-teal/30 transition group flex flex-col justify-between"
        >
          <div>
            <div className="w-12 h-12 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center mb-4 group-hover:scale-105 transition">
              <ShieldCheck size={22} />
            </div>
            <h3 className="font-bold text-navy text-base mb-1">Billing & Plan</h3>
            <p className="text-xs text-blue-grey leading-relaxed">
              Manage your 30-day free trial, review the ₹200/month recurring subscription, or cancel anytime.
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-50 flex items-center text-xs font-semibold text-emerald-600 gap-1">
            Manage plan <ChevronRight size={14} />
          </div>
        </Link>
      </div>

      {/* Recent Uploads Section */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-lg font-bold text-navy">Recent Reports</h2>
            <p className="text-xs text-blue-grey">Your latest medical document explanations</p>
          </div>
          <Link
            href="/dashboard/reports"
            className="text-xs font-semibold text-teal hover:text-teal-dark flex items-center gap-1"
          >
            All Reports <ArrowRight size={14} />
          </Link>
        </div>

        {loading ? (
          <div className="py-12 text-center text-sm text-blue-grey flex items-center justify-center gap-2">
            <RefreshCw size={16} className="animate-spin text-teal" /> Loading your reports...
          </div>
        ) : reports.length === 0 ? (
          <div className="py-12 text-center border-2 border-dashed border-slate-200 rounded-xl">
            <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto mb-3">
              <FileText size={22} />
            </div>
            <h3 className="font-semibold text-navy text-sm mb-1">No reports uploaded yet</h3>
            <p className="text-xs text-blue-grey max-w-sm mx-auto mb-4">
              Upload your first lab test report (PDF, image, or scan) to receive structured explanations and discussion questions.
            </p>
            <Link href="/dashboard/upload" className="btn-primary text-xs !py-2 !px-4">
              <Upload size={14} /> Upload First Report
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {reports.map((report) => (
              <div
                key={report.id}
                className="py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/50 rounded-xl px-2 transition"
              >
                <div className="flex items-center gap-3.5">
                  <div className="w-10 h-10 rounded-xl bg-teal/10 text-teal flex items-center justify-center shrink-0">
                    <Activity size={18} />
                  </div>
                  <div>
                    <h4 className="font-semibold text-sm text-navy">{report.report_name}</h4>
                    <div className="flex items-center gap-3 text-xs text-blue-grey mt-0.5">
                      <span className="flex items-center gap-1">
                        <Calendar size={12} /> {formatDate(report.created_at)}
                      </span>
                      <span className="uppercase text-[10px] font-bold tracking-wider px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                        {report.file_type}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3 self-end sm:self-center">
                  <span
                    className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                      report.processing_status === 'COMPLETED'
                        ? 'bg-green-100 text-green-700'
                        : report.processing_status === 'FAILED'
                        ? 'bg-red-100 text-red-700'
                        : report.processing_status === 'NEEDS_REVIEW'
                        ? 'bg-amber-100 text-amber-700'
                        : 'bg-blue-100 text-blue-700'
                    }`}
                  >
                    {report.processing_status === 'COMPLETED'
                      ? 'Completed'
                      : report.processing_status === 'NEEDS_REVIEW'
                      ? 'Needs Review'
                      : report.processing_status === 'FAILED'
                      ? 'Failed'
                      : 'Processing'}
                  </span>
                  <Link
                    href={`/dashboard/report/${report.id}`}
                    className="btn-outline !py-1.5 !px-3 text-xs inline-flex items-center gap-1"
                  >
                    View Analysis <ChevronRight size={12} />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Safety Notice */}
      <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
        <div className="text-xs text-amber-900 leading-relaxed">
          <strong>Important Medical Notice:</strong> MediExplain AI extracts and organizes test values to help you prepare for discussions with healthcare professionals. It does not provide medical diagnoses, treatment instructions, or prescriptions. Always consult your qualified doctor regarding your lab results.
        </div>
      </div>
    </div>
  );
}

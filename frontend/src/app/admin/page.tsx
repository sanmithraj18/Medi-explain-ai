'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { 
  ShieldAlert, Users, Activity, ArrowLeft, 
  CheckCircle2, TrendingUp, RefreshCw, Lock
} from 'lucide-react';
import { createClient } from '@/lib/supabase/client';

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const backendUrl = (process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

  useEffect(() => {
    async function fetchAdminStats() {
      try {
        const supabase = createClient();
        const { data: { session } } = await supabase.auth.getSession();
        const user = session?.user;

        if (!user) {
          setErrorMsg('Authentication required.');
          setLoading(false);
          return;
        }

        const headers: Record<string, string> = {};
        if (session?.access_token) {
          headers['Authorization'] = `Bearer ${session.access_token}`;
        }

        const res = await fetch(`${backendUrl}/api/v1/admin/stats`, { headers });
        if (!res.ok) {
          if (res.status === 403) {
            setErrorMsg('Access denied. Administrator privileges required.');
          } else {
            setErrorMsg('Failed to load administrator statistics.');
          }
          return;
        }

        const data = await res.json();
        setStats(data);
      } catch (err: any) {
        setErrorMsg(err.message || 'Error communicating with administration backend.');
      } finally {
        setLoading(false);
      }
    }

    fetchAdminStats();
  }, [backendUrl]);

  if (loading) {
    return (
      <div className="min-h-screen bg-surface flex items-center justify-center p-6">
        <div className="flex items-center gap-3 text-sm text-blue-grey">
          <RefreshCw size={20} className="animate-spin text-teal" /> Loading administrator metrics...
        </div>
      </div>
    );
  }

  if (errorMsg) {
    return (
      <div className="min-h-screen bg-surface flex items-center justify-center p-6">
        <div className="bg-white p-8 rounded-2xl border border-red-200 shadow-card max-w-md w-full text-center space-y-4">
          <div className="w-12 h-12 bg-red-100 text-red-600 rounded-full flex items-center justify-center mx-auto">
            <Lock size={22} />
          </div>
          <h2 className="text-lg font-bold text-navy">Restricted Administration View</h2>
          <p className="text-xs text-blue-grey">{errorMsg}</p>
          <Link href="/dashboard" className="btn-primary !py-2 !px-4 text-xs inline-flex">
            <ArrowLeft size={14} /> Return to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface p-6 sm:p-10">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Top Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
          <div>
            <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-navy text-white rounded-full text-[11px] font-bold tracking-wider uppercase mb-2">
              <Lock size={12} className="text-teal-light" /> Admin Operations
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-navy">
              MediExplain AI Platform Metrics
            </h1>
            <p className="text-xs text-blue-grey mt-0.5">
              Verified business health and operational telemetry (Timezone: Asia/Kolkata)
            </p>
          </div>

          <Link href="/dashboard" className="btn-outline !py-2 !px-4 text-xs self-start sm:self-auto">
            <ArrowLeft size={14} /> User Dashboard
          </Link>
        </div>

        {/* Security Banner */}
        <div className="p-4 bg-slate-900 text-slate-200 rounded-2xl flex items-start gap-3 text-xs leading-relaxed">
          <ShieldAlert size={18} className="text-teal-light shrink-0 mt-0.5" />
          <div>
            <strong className="text-white">Medical Confidentiality Policy:</strong> In compliance with healthcare data protection principles, this administrative view contains aggregate usage and billing numbers only. Individual user medical report files, health test records, and patient parameters are strictly hidden from administrative consoles.
          </div>
        </div>

        {/* High-level KPI Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-card space-y-2">
            <div className="flex items-center justify-between text-blue-grey text-xs font-semibold">
              <span>Total Registered Users</span>
              <Users size={18} className="text-teal" />
            </div>
            <div className="text-3xl font-extrabold text-navy">
              {stats?.total_users || 0}
            </div>
            <p className="text-[11px] text-slate-400">Total verified user profiles</p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-card space-y-2">
            <div className="flex items-center justify-between text-blue-grey text-xs font-semibold">
              <span>Active Trials (30 Days)</span>
              <Activity size={18} className="text-blue-600" />
            </div>
            <div className="text-3xl font-extrabold text-navy">
              {stats?.subscriptions?.trial_active || 0}
            </div>
            <p className="text-[11px] text-slate-400">Eligible for free premium features</p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-card space-y-2">
            <div className="flex items-center justify-between text-blue-grey text-xs font-semibold">
              <span>Active Subscriptions</span>
              <CheckCircle2 size={18} className="text-emerald-600" />
            </div>
            <div className="text-3xl font-extrabold text-navy">
              {stats?.subscriptions?.active || 0}
            </div>
            <p className="text-[11px] text-slate-400">₹200/mo recurring billing active</p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-card space-y-2">
            <div className="flex items-center justify-between text-blue-grey text-xs font-semibold">
              <span>Total Verified Revenue</span>
              <TrendingUp size={18} className="text-teal-dark" />
            </div>
            <div className="text-3xl font-extrabold text-teal-dark">
              ₹{(stats?.payments?.total_revenue_inr || 0).toLocaleString('en-IN')}
            </div>
            <p className="text-[11px] text-slate-400">From verified captured payments</p>
          </div>
        </div>

        {/* Detailed Breakdown Panels */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Subscription State Breakdown */}
          <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-card space-y-4">
            <h3 className="font-bold text-navy text-sm">Subscription State Breakdown</h3>
            <div className="space-y-3 text-xs">
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
                <span className="font-medium text-navy">Active 30-Day Trials</span>
                <span className="font-bold text-teal">{stats?.subscriptions?.trial_active || 0}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
                <span className="font-medium text-navy">Active Paying Customers</span>
                <span className="font-bold text-emerald-600">{stats?.subscriptions?.active || 0}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
                <span className="font-medium text-navy">Expired Trials (Not Subscribed)</span>
                <span className="font-bold text-amber-600">{stats?.subscriptions?.trial_expired || 0}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
                <span className="font-medium text-navy">Cancelled Subscriptions</span>
                <span className="font-bold text-slate-600">{stats?.subscriptions?.cancelled || 0}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
                <span className="font-medium text-navy">Payment Failed</span>
                <span className="font-bold text-red-600">{stats?.subscriptions?.payment_failed || 0}</span>
              </div>
            </div>
          </div>

          {/* Payment & Ingestion Telemetry */}
          <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-card space-y-4">
            <h3 className="font-bold text-navy text-sm">Gateway & Document Telemetry</h3>
            <div className="space-y-3 text-xs">
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
                <span className="font-medium text-navy">Successful Payment Transactions</span>
                <span className="font-bold text-emerald-600">{stats?.payments?.successful_count || 0}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
                <span className="font-medium text-navy">Failed Payment Transactions</span>
                <span className="font-bold text-red-600">{stats?.payments?.failed_count || 0}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
                <span className="font-medium text-navy">Total Medical Documents Uploaded</span>
                <span className="font-bold text-navy">{stats?.reports?.total || 0}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
                <span className="font-medium text-navy">Reports Successfully Explained</span>
                <span className="font-bold text-teal">{stats?.reports?.completed || 0}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

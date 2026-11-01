'use client';

import { useEffect, useState, useCallback } from 'react';
import Script from 'next/script';
import { 
  CheckCircle2, XCircle, ArrowRight, Shield
} from 'lucide-react';
import { createClient } from '@/lib/supabase/client';
import { formatCurrency, formatDate, daysUntil } from '@/lib/utils';
import { toast } from 'sonner';

declare global {
  interface Window {
    Razorpay: any;
  }
}

export default function BillingManagementPage() {
  const [subscription, setSubscription] = useState<any>(null);
  const [payments, setPayments] = useState<any[]>([]);
  const [authorizing, setAuthorizing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [showConsentModal, setShowConsentModal] = useState(false);

  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';

  const fetchBillingData = useCallback(async () => {
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const headers: Record<string, string> = {};
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
      }

      // 1. Fetch live subscription & trial state from backend API (server-validated)
      try {
        const subRes = await fetch(`${backendUrl}/api/v1/subscriptions/current`, { headers });
        if (subRes.ok) {
          const subData = await subRes.json();
          setSubscription(subData);
          if (subData.payments) {
            setPayments(subData.payments);
          }
          return;
        }
      } catch {
        // Fallback to Supabase direct query if backend is unreachable
      }

      // Fallback: direct Supabase query
      const user = session?.user;
      if (user) {
        const { data: subData } = await supabase
          .from('subscriptions')
          .select('*')
          .eq('user_id', user.id)
          .maybeSingle();

        if (subData) {
          setSubscription(subData);
        }

        const { data: paymentsData } = await supabase
          .from('payments')
          .select('*')
          .eq('user_id', user.id)
          .order('created_at', { ascending: false });

        if (paymentsData) {
          setPayments(paymentsData);
        }
      }
    } catch (err: any) {
      console.error('Error loading billing:', err);
    }
  }, [backendUrl]);

  useEffect(() => {
    fetchBillingData();
  }, [fetchBillingData]);

  const handleStartRecurringMandate = async () => {
    setAuthorizing(true);
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const user = session?.user;
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
      }

      // Call backend to create Razorpay subscription
      const res = await fetch(`${backendUrl}/api/v1/subscriptions/create-checkout`, {
        method: 'POST',
        headers,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to create subscription checkout' }));
        throw new Error(err.detail || 'Could not initiate checkout');
      }

      const checkoutData = await res.json();

      // Launch official Razorpay Checkout modal
      if (!window.Razorpay) {
        throw new Error('Razorpay SDK failed to load. Please check your internet connection.');
      }

      const options = {
        key: checkoutData.razorpay_key_id || process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID,
        subscription_id: checkoutData.gateway_subscription_id,
        name: 'MediExplain AI',
        description: 'Monthly Recurring Subscription (₹200/mo after trial)',
        image: 'https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=128&q=80',
        handler: async function (response: any) {
          // Verify on backend
          try {
            const verifyRes = await fetch(`${backendUrl}/api/v1/subscriptions/verify-checkout`, {
              method: 'POST',
              headers,
              body: JSON.stringify({
                razorpay_payment_id: response.razorpay_payment_id || 'mandate_auth',
                razorpay_subscription_id: response.razorpay_subscription_id,
                razorpay_signature: response.razorpay_signature,
              }),
            });

            if (verifyRes.ok) {
              toast.success('Recurring subscription authorized successfully!');
              setShowConsentModal(false);
              await fetchBillingData();
            } else {
              toast.error('Mandate verification could not be completed.');
            }
          } catch (err: any) {
            toast.error(err.message || 'Verification failed');
          }
        },
        prefill: {
          name: user?.user_metadata?.full_name || '',
          email: user?.email || '',
        },
        theme: {
          color: '#0d9488', // Teal brand color
        },
      };

      const rzp = new window.Razorpay(options);
      rzp.on('payment.failed', function (resp: any) {
        toast.error(`Payment failed: ${resp.error.description}`);
      });
      rzp.open();
    } catch (err: any) {
      toast.error(err.message || 'Failed to initiate authorization');
    } finally {
      setAuthorizing(false);
    }
  };

  const handleCancelSubscription = async () => {
    if (!confirm('Are you sure you want to cancel your recurring subscription? You will retain access until the end of the current period.')) {
      return;
    }

    setCancelling(true);
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const headers: Record<string, string> = {};
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
      }

      const res = await fetch(`${backendUrl}/api/v1/subscriptions/cancel`, {
        method: 'POST',
        headers,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to cancel subscription' }));
        throw new Error(err.detail);
      }

      const data = await res.json();
      toast.success(data.message || 'Subscription cancelled successfully');
      await fetchBillingData();
    } catch (err: any) {
      toast.error(err.message || 'Cancellation failed');
    } finally {
      setCancelling(false);
    }
  };

  const trialDaysRemaining = subscription?.trial_end_date 
    ? Math.max(0, daysUntil(subscription.trial_end_date) ?? 0)
    : 30;

  return (
    <>
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="lazyOnload" />

      <div className="space-y-8 max-w-4xl mx-auto">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-navy">
            Billing & Subscription Management
          </h1>
          <p className="text-sm text-blue-grey mt-1">
            Manage your plan, free trial status, recurring mandate, and invoice history.
          </p>
        </div>

        {/* Current Plan Card */}
        <div className="bg-white rounded-2xl p-6 sm:p-8 border-2 border-teal shadow-card relative">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-100">
            <div>
              <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-teal/10 rounded-full text-xs font-semibold text-teal-dark mb-2">
                <CheckCircle2 size={14} /> Active Plan
              </div>
              <h2 className="text-2xl font-bold text-navy">
                MediExplain AI Premium
              </h2>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-3xl font-extrabold text-navy">₹200</span>
                <span className="text-xs text-blue-grey">/ month</span>
              </div>
            </div>

            <div className="text-left sm:text-right space-y-1">
              <span
                className={`text-xs font-bold px-3 py-1 rounded-full inline-block ${
                  subscription?.subscription_status === 'ACTIVE'
                    ? 'bg-green-100 text-green-700'
                    : subscription?.subscription_status === 'TRIAL_ACTIVE'
                    ? 'bg-teal/10 text-teal-dark'
                    : subscription?.subscription_status === 'CANCELED' || subscription?.subscription_status === 'CANCELLED'
                    ? 'bg-slate-100 text-slate-600'
                    : subscription?.subscription_status === 'PAST_DUE'
                    ? 'bg-red-100 text-red-700'
                    : 'bg-amber-100 text-amber-700'
                }`}
              >
                Status: {subscription?.subscription_status || 'TRIAL_ACTIVE'}
              </span>
              {subscription?.trial_end_date && subscription?.subscription_status === 'TRIAL_ACTIVE' && (
                <p className="text-xs text-blue-grey font-medium">
                  Trial ends: {formatDate(subscription.trial_end_date)} ({trialDaysRemaining} days remaining)
                </p>
              )}
              {subscription?.next_billing_date && (
                <p className="text-xs text-blue-grey font-medium">
                  Next debit date: {formatDate(subscription.next_billing_date)}
                </p>
              )}
            </div>
          </div>

          {/* Plan Details & Explicit Consent CTA */}
          <div className="py-6 space-y-4">
            <h3 className="text-xs uppercase font-bold text-slate-400 tracking-wider">
              Included Features
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs text-navy">
              {[
                'Unlimited PDF & Image report uploads',
                'Camera scanning on mobile & tablet',
                'OCR text & parameter extraction',
                'Structured AI clinical explanations',
                'Personalized doctor discussion questions',
                'Historical parameter tracking',
                'Encrypted private cloud storage',
                'Priority email support',
              ].map((f) => (
                <div key={f} className="flex items-center gap-2">
                  <CheckCircle2 size={16} className="text-teal shrink-0" />
                  <span>{f}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Action Row */}
          <div className="pt-6 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="text-xs text-blue-grey">
              {subscription?.subscription_status === 'CANCELED' || subscription?.subscription_status === 'CANCELLED' ? (
                <span>Your subscription has been cancelled. No further debits will occur.</span>
              ) : subscription?.gateway_subscription_id ? (
                <span>Recurring mandate active via Razorpay Subscriptions.</span>
              ) : (
                <span>Free trial active. Authorize recurring mandate to continue uninterrupted.</span>
              )}
            </div>

            <div className="flex items-center gap-3 w-full sm:w-auto">
              {subscription?.subscription_status !== 'CANCELED' && subscription?.subscription_status !== 'CANCELLED' && 
               (!subscription?.gateway_subscription_id || subscription?.subscription_status === 'TRIAL_ACTIVE') && (
                <button
                  onClick={() => setShowConsentModal(true)}
                  disabled={authorizing}
                  className="btn-primary text-xs !py-2.5 !px-5 w-full sm:w-auto justify-center shadow-md"
                >
                  Authorize Recurring Plan (₹200/mo) <ArrowRight size={14} />
                </button>
              )}

              {subscription?.subscription_status !== 'CANCELED' && subscription?.subscription_status !== 'CANCELLED' && (
                <button
                  onClick={handleCancelSubscription}
                  disabled={cancelling}
                  className="px-4 py-2 text-xs font-semibold text-red-600 hover:bg-red-50 rounded-lg border border-red-200 transition"
                >
                  {cancelling ? 'Cancelling...' : 'Cancel Subscription'}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Payment History Table */}
        <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-card space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-navy text-base">Payment History</h3>
              <p className="text-xs text-blue-grey">Verified transaction records from Razorpay</p>
            </div>
          </div>

          {payments.length === 0 ? (
            <div className="py-8 text-center text-xs text-blue-grey">
              No payment transactions yet. Free trials do not generate charges until the first scheduled debit.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-100 text-[10px] uppercase font-bold text-slate-400">
                  <tr>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Payment ID</th>
                    <th className="px-4 py-3">Amount</th>
                    <th className="px-4 py-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {payments.map((p) => (
                    <tr key={p.id}>
                      <td className="px-4 py-3">{formatDate(p.payment_date || p.created_at)}</td>
                      <td className="px-4 py-3 font-mono text-slate-500">{p.gateway_payment_id}</td>
                      <td className="px-4 py-3 font-bold text-navy">{formatCurrency(p.amount, p.currency)}</td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-green-100 text-green-700">
                          {p.payment_status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Explicit Disclosure Box */}
        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2 text-navy font-bold text-xs">
            <Shield size={16} className="text-teal" /> Recurring Payment Disclosure & Policy
          </div>
          <p className="text-xs text-blue-grey leading-relaxed">
            By setting up recurring payments, you authorize MediExplain AI to charge ₹200 (including applicable taxes) every month automatically through Razorpay after your 30-day trial expires. You will receive notification prior to each charge. You may cancel at any time from this dashboard without cancellation fees.
          </p>
        </div>
      </div>

      {/* Explicit Recurring Consent Modal */}
      {showConsentModal && (
        <div className="fixed inset-0 z-50 bg-navy/50 flex items-center justify-center p-4 backdrop-blur-xs">
          <div className="bg-white rounded-2xl p-6 sm:p-8 max-w-lg w-full shadow-xl space-y-5 border border-slate-100">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-bold text-navy text-lg">
                Authorize Monthly Subscription
              </h3>
              <button
                onClick={() => setShowConsentModal(false)}
                className="text-slate-400 hover:text-navy"
              >
                <XCircle size={20} />
              </button>
            </div>

            <div className="space-y-3 text-xs text-slate-700 leading-relaxed">
              <div className="p-3 bg-teal/10 rounded-xl text-teal-dark font-medium">
                <strong>Plan:</strong> MediExplain AI Premium — ₹200 / month
              </div>

              <div className="space-y-2 p-3 bg-slate-50 rounded-xl">
                <p>
                  <strong>Free Period:</strong> 30 calendar days from registration.
                </p>
                <p>
                  <strong>First Automatic Debit:</strong> Scheduled on {formatDate(subscription?.trial_end_date)}.
                </p>
                <p>
                  <strong>Mandate Authentication:</strong> Razorpay or your bank may perform an authentication check (e.g. ₹0 or ₹1 refundable charge) to register your recurring mandate (UPI Autopay / Card).
                </p>
                <p>
                  <strong>Cancellation:</strong> You can cancel anytime before your trial ends from your Billing page to prevent the first ₹200 charge.
                </p>
              </div>

              <p className="text-[11px] text-slate-500">
                By clicking &quot;Proceed to Razorpay Mandate&quot;, you grant explicit consent for recurring automatic monthly debits of ₹200 until cancelled.
              </p>
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <button
                onClick={() => setShowConsentModal(false)}
                className="btn-outline !py-2 !px-4 text-xs"
              >
                Back
              </button>
              <button
                onClick={handleStartRecurringMandate}
                disabled={authorizing}
                className="btn-primary !py-2 !px-5 text-xs shadow-md"
              >
                {authorizing ? 'Opening Razorpay...' : 'Proceed to Razorpay Mandate'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

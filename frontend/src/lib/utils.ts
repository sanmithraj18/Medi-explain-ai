import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { differenceInDays, format, parseISO } from 'date-fns';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(paise: number, currency = 'INR'): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
  }).format(paise / 100);
}

export function formatDate(dateStr?: string | null): string {
  if (!dateStr) return '—';
  try {
    return format(parseISO(dateStr), 'dd MMM yyyy');
  } catch {
    return '—';
  }
}

export function daysUntil(dateStr?: string | null): number | null {
  if (!dateStr) return null;
  try {
    return differenceInDays(parseISO(dateStr), new Date());
  } catch {
    return null;
  }
}

export function getStatusColor(status: string): string {
  const map: Record<string, string> = {
    TRIAL_ACTIVE: 'bg-teal/10 text-teal-dark',
    ACTIVE: 'bg-green-100 text-green-700',
    TRIAL_EXPIRED: 'bg-amber-100 text-amber-700',
    PAYMENT_FAILED: 'bg-red-100 text-red-700',
    CANCELLED: 'bg-slate-100 text-slate-600',
    HALTED: 'bg-orange-100 text-orange-700',
    AUTHORIZATION_PENDING: 'bg-blue-100 text-blue-700',
  };
  return map[status] ?? 'bg-slate-100 text-slate-600';
}

export function getParameterStatusColor(flag?: string): string {
  if (flag === 'H' || flag === 'CRITICAL') return 'text-red-600 bg-red-50';
  if (flag === 'L') return 'text-blue-600 bg-blue-50';
  if (flag === 'N') return 'text-green-600 bg-green-50';
  return 'text-slate-600 bg-slate-50';
}

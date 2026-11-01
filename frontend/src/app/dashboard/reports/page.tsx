'use client';

import { useEffect, useState, useMemo } from 'react';
import Link from 'next/link';
import { 
  FileText, Download, Trash2, 
  Search, Upload, RefreshCw, Eye,
  SlidersHorizontal, ArrowUpDown, Calendar,
  CheckCircle2, Clock, AlertCircle
} from 'lucide-react';
import { createClient } from '@/lib/supabase/client';
import { formatDate } from '@/lib/utils';
import { toast } from 'sonner';

type StatusFilter = 'ALL' | 'COMPLETED' | 'NEEDS_REVIEW' | 'PROCESSING' | 'FAILED';
type SortOption = 'NEWEST' | 'OLDEST' | 'NAME_ASC' | 'NAME_DESC';

export default function ReportsHistoryPage() {
  const [reports, setReports] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  const [sortBy, setSortBy] = useState<SortOption>('NEWEST');
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchReports = async () => {
    try {
      const supabase = createClient();
      const { data: { user } } = await supabase.auth.getUser();

      if (user) {
        const { data, error } = await supabase
          .from('medical_reports')
          .select('*')
          .eq('user_id', user.id)
          .order('created_at', { ascending: false });

        if (error) throw error;
        setReports(data || []);
      }
    } catch (err: any) {
      console.error('Failed to load reports:', err);
      toast.error('Could not load report history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  const handleDownload = async (reportId: string) => {
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';

      const headers: Record<string, string> = {};
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
      }

      const res = await fetch(`${backendUrl}/api/v1/reports/${reportId}/download-url`, { headers });
      if (!res.ok) throw new Error('Could not obtain secure download link');

      const data = await res.json();
      if (data.signed_url) {
        window.open(data.signed_url, '_blank');
      }
    } catch (err: any) {
      toast.error(err.message || 'Download failed');
    }
  };

  const handleDelete = async (reportId: string) => {
    if (!confirm('Are you sure you want to permanently delete this report and all associated analyses?')) {
      return;
    }

    setDeletingId(reportId);
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';

      const headers: Record<string, string> = {};
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
      }

      const res = await fetch(`${backendUrl}/api/v1/reports/${reportId}`, {
        method: 'DELETE',
        headers,
      });

      if (!res.ok) throw new Error('Failed to delete report');

      toast.success('Report deleted successfully');
      setReports((prev) => prev.filter((r) => r.id !== reportId));
    } catch (err: any) {
      toast.error(err.message || 'Failed to delete report');
    } finally {
      setDeletingId(null);
    }
  };

  // Filter & Sort Logic
  const filteredAndSortedReports = useMemo(() => {
    let result = reports.filter((r) => {
      // 1. Search Query
      const matchesSearch = r.report_name?.toLowerCase().includes(searchQuery.toLowerCase());
      if (!matchesSearch) return false;

      // 2. Status Filter
      if (statusFilter === 'ALL') return true;
      if (statusFilter === 'COMPLETED') return r.processing_status === 'COMPLETED';
      if (statusFilter === 'NEEDS_REVIEW') return r.processing_status === 'NEEDS_REVIEW';
      if (statusFilter === 'FAILED') return r.processing_status === 'FAILED';
      if (statusFilter === 'PROCESSING') {
        return ['PENDING', 'EXTRACTING', 'ANALYZING'].includes(r.processing_status);
      }
      return true;
    });

    // 3. Sorting
    result = [...result].sort((a, b) => {
      if (sortBy === 'NEWEST') {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
      if (sortBy === 'OLDEST') {
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      }
      if (sortBy === 'NAME_ASC') {
        return (a.report_name || '').localeCompare(b.report_name || '');
      }
      if (sortBy === 'NAME_DESC') {
        return (b.report_name || '').localeCompare(a.report_name || '');
      }
      return 0;
    });

    return result;
  }, [reports, searchQuery, statusFilter, sortBy]);

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-navy">
            Medical Reports History
          </h1>
          <p className="text-sm text-blue-grey mt-1">
            Access, search, and manage your uploaded laboratory documents and explanations.
          </p>
        </div>

        <Link href="/dashboard/upload" className="btn-primary text-xs !py-2.5 !px-4 self-start sm:self-auto inline-flex items-center gap-2 shadow-sm">
          <Upload size={16} /> Upload New Report
        </Link>
      </div>

      {/* Filter & Controls Bar */}
      <div className="bg-white p-4 rounded-2xl border border-slate-100 shadow-card space-y-4">
        <div className="flex flex-col sm:flex-row items-center gap-3">
          {/* Search Input */}
          <div className="relative w-full sm:flex-1">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search reports by title or test name..."
              className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm text-navy placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal"
            />
          </div>

          {/* Sort Selector */}
          <div className="flex items-center gap-2 w-full sm:w-auto shrink-0">
            <ArrowUpDown size={15} className="text-blue-grey hidden sm:block" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-semibold text-navy focus:outline-none focus:ring-2 focus:ring-teal w-full sm:w-auto"
            >
              <option value="NEWEST">Newest First</option>
              <option value="OLDEST">Oldest First</option>
              <option value="NAME_ASC">Name (A–Z)</option>
              <option value="NAME_DESC">Name (Z–A)</option>
            </select>
          </div>
        </div>

        {/* Status Filter Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
          <span className="text-blue-grey font-medium mr-1 text-[11px] flex items-center gap-1">
            <SlidersHorizontal size={12} /> Status:
          </span>
          {(['ALL', 'COMPLETED', 'NEEDS_REVIEW', 'PROCESSING', 'FAILED'] as StatusFilter[]).map((st) => {
            const active = statusFilter === st;
            return (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-3 py-1 rounded-full font-semibold transition whitespace-nowrap ${
                  active
                    ? 'bg-teal text-white shadow-xs'
                    : 'bg-slate-100 text-blue-grey hover:bg-slate-200 hover:text-navy'
                }`}
              >
                {st === 'ALL'
                  ? 'All Reports'
                  : st === 'COMPLETED'
                  ? 'Completed'
                  : st === 'NEEDS_REVIEW'
                  ? 'Needs Review'
                  : st === 'PROCESSING'
                  ? 'In Progress'
                  : 'Failed'}
              </button>
            );
          })}
        </div>
      </div>

      {/* Reports Table / Card Container */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
        {loading ? (
          <div className="py-20 text-center text-sm text-blue-grey flex items-center justify-center gap-2">
            <RefreshCw size={18} className="animate-spin text-teal" /> Loading report records...
          </div>
        ) : filteredAndSortedReports.length === 0 ? (
          <div className="py-16 text-center px-4">
            <div className="w-14 h-14 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto mb-3">
              <FileText size={26} />
            </div>
            <h3 className="font-bold text-navy text-base mb-1">
              {searchQuery || statusFilter !== 'ALL'
                ? 'No matching reports found'
                : 'No medical reports saved yet'}
            </h3>
            <p className="text-xs text-blue-grey max-w-sm mx-auto mb-5">
              {searchQuery || statusFilter !== 'ALL'
                ? 'Try adjusting your search terms or status filter.'
                : 'Upload your lab tests to keep an organized history and track key parameters over time.'}
            </p>
            {searchQuery || statusFilter !== 'ALL' ? (
              <button
                onClick={() => {
                  setSearchQuery('');
                  setStatusFilter('ALL');
                }}
                className="btn-outline text-xs !py-2 !px-4"
              >
                Clear Filters
              </button>
            ) : (
              <Link href="/dashboard/upload" className="btn-primary text-xs !py-2.5 !px-5 inline-flex items-center gap-2">
                <Upload size={16} /> Upload First Document
              </Link>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50/80 border-b border-slate-100 text-[11px] font-bold text-blue-grey uppercase tracking-wider">
                <tr>
                  <th className="px-6 py-3.5">Report Title</th>
                  <th className="px-6 py-3.5">Uploaded Date</th>
                  <th className="px-6 py-3.5">Document Format</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredAndSortedReports.map((report) => (
                  <tr key={report.id} className="hover:bg-slate-50/60 transition">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-teal/10 text-teal flex items-center justify-center shrink-0">
                          <FileText size={18} />
                        </div>
                        <span className="font-semibold text-navy">
                          {report.report_name}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-blue-grey text-xs">
                      <span className="flex items-center gap-1.5">
                        <Calendar size={13} className="text-slate-400" />
                        {formatDate(report.created_at)}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="uppercase text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                        {report.file_type}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                          report.processing_status === 'COMPLETED'
                            ? 'bg-green-100 text-green-700'
                            : report.processing_status === 'FAILED'
                            ? 'bg-red-100 text-red-700'
                            : report.processing_status === 'NEEDS_REVIEW'
                            ? 'bg-amber-100 text-amber-700'
                            : 'bg-blue-100 text-blue-700 animate-pulse'
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
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Link
                          href={`/dashboard/report/${report.id}`}
                          className="p-2 rounded-lg text-teal hover:bg-teal/10 transition inline-flex items-center gap-1 text-xs font-semibold"
                          title="View Analysis"
                        >
                          <Eye size={16} /> View
                        </Link>
                        <button
                          onClick={() => handleDownload(report.id)}
                          className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 transition"
                          title="Download Original (60-minute signed URL)"
                        >
                          <Download size={16} />
                        </button>
                        <button
                          onClick={() => handleDelete(report.id)}
                          disabled={deletingId === report.id}
                          className="p-2 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition disabled:opacity-50"
                          title="Delete Report"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

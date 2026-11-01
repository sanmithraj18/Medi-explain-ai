'use client';

import { useEffect, useState, use, useCallback } from 'react';
import Link from 'next/link';
import { 
  Activity, ArrowLeft, Brain, Sparkles, CheckCircle2, 
  AlertTriangle, Copy, Check, MessageSquare,
  Printer, ShieldAlert, RefreshCw, FileText, X, CheckCheck, Edit2
} from 'lucide-react';
import { createClient } from '@/lib/supabase/client';
import { formatDate } from '@/lib/utils';
import { toast } from 'sonner';

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ReportDetailPage({ params }: PageProps) {
  const resolvedParams = use(params);
  const reportId = resolvedParams.id;

  const [report, setReport] = useState<any>(null);
  const [parameters, setParameters] = useState<any[]>([]);
  const [analysis, setAnalysis] = useState<any>(null);
  const [questions, setQuestions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Raw text viewer state
  const [showRawText, setShowRawText] = useState(false);
  const [rawText, setRawText] = useState<string>('');

  // Editing / confirming parameters
  const [editingParamId, setEditingParamId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>('');
  const [editUnit, setEditUnit] = useState<string>('');
  const [confirming, setConfirming] = useState(false);

  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';

  const loadData = useCallback(async () => {
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const headers: Record<string, string> = {};
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
      }

      // Fetch Report Metadata
      const reportRes = await fetch(`${backendUrl}/api/v1/reports/${reportId}`, { headers });
      if (reportRes.ok) {
        const rData = await reportRes.json();
        setReport(rData);
        setRawText(rData.raw_extracted_text || '');
      }

      // Fetch Extracted Parameters
      const paramRes = await fetch(`${backendUrl}/api/v1/reports/${reportId}/parameters`, { headers });
      if (paramRes.ok) {
        const pData = await paramRes.json();
        setParameters(pData.parameters || []);
      }

      // Fetch Analysis (if already generated)
      const analysisRes = await fetch(`${backendUrl}/api/v1/analysis/${reportId}`, { headers });
      if (analysisRes.ok) {
        const aData = await analysisRes.json();
        setAnalysis(aData);
      }

      // Fetch Doctor Questions
      const questionsRes = await fetch(`${backendUrl}/api/v1/questions/report/${reportId}`, { headers });
      if (questionsRes.ok) {
        const qData = await questionsRes.json();
        setQuestions(qData.questions || []);
      }
    } catch (err: any) {
      console.error('Error fetching report details:', err);
    } finally {
      setLoading(false);
    }
  }, [backendUrl, reportId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleTriggerAnalysis = async () => {
    setAnalyzing(true);
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
      }

      const res = await fetch(`${backendUrl}/api/v1/analysis/${reportId}/trigger`, {
        method: 'POST',
        headers,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Analysis failed' }));
        throw new Error(err.detail || 'Could not generate AI explanation');
      }

      toast.success('Medical explanation generated successfully!');
      await loadData();
    } catch (err: any) {
      toast.error(err.message || 'AI analysis failed');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleCopyQuestion = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success('Question copied to clipboard');
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleToggleQuestionStatus = async (qId: string, currentStatus: string) => {
    const nextStatus = currentStatus === 'DISCUSSED' ? 'PENDING' : 'DISCUSSED';
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
      }

      const res = await fetch(`${backendUrl}/api/v1/questions/${qId}/status`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify({ discussion_status: nextStatus }),
      });

      if (res.ok) {
        setQuestions((prev) =>
          prev.map((q) => (q.id === qId ? { ...q, discussion_status: nextStatus } : q))
        );
      }
    } catch (err) {
      console.error('Failed to update status:', err);
    }
  };

  // Confirm or adjust a parameter flagged for user review
  const handleConfirmParameter = async (paramId: string) => {
    setConfirming(true);
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
      }

      const payload: any = { user_confirmed: true };
      if (editValue.trim()) payload.observed_value = editValue.trim();
      if (editUnit.trim()) payload.unit = editUnit.trim();

      const res = await fetch(`${backendUrl}/api/v1/reports/${reportId}/parameters/${paramId}/confirm`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error('Failed to confirm parameter');
      }

      toast.success('Value verified and confirmed!');
      setEditingParamId(null);
      await loadData();
    } catch (err: any) {
      toast.error(err.message || 'Error confirming parameter');
    } finally {
      setConfirming(false);
    }
  };

  if (loading) {
    return (
      <div className="py-24 text-center text-sm text-blue-grey flex flex-col items-center justify-center gap-3">
        <RefreshCw size={24} className="animate-spin text-teal" />
        <p>Loading report analysis...</p>
      </div>
    );
  }

  const overall = analysis?.overall_summary;
  const detailed = analysis?.detailed_explanation || {};

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* Top Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
        <Link
          href="/dashboard/reports"
          className="inline-flex items-center gap-2 text-xs font-semibold text-blue-grey hover:text-navy transition"
        >
          <ArrowLeft size={16} /> Back to Reports
        </Link>
        <div className="flex items-center gap-2.5">
          {rawText && (
            <button
              onClick={() => setShowRawText(true)}
              className="btn-outline !py-1.5 !px-3 text-xs inline-flex items-center gap-1.5 text-blue-grey"
            >
              <FileText size={14} /> View Original OCR Text
            </button>
          )}
          <button
            onClick={() => window.print()}
            className="btn-outline !py-1.5 !px-3 text-xs inline-flex items-center gap-1.5"
          >
            <Printer size={14} /> Print / Save PDF
          </button>
        </div>
      </div>

      {/* Report Header Banner */}
      <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="uppercase text-[10px] font-bold px-2 py-0.5 rounded bg-teal/10 text-teal-dark">
              {report?.file_type} Document
            </span>
            <span className="text-xs text-blue-grey">
              Uploaded {formatDate(report?.created_at)}
            </span>
            <span className="text-xs font-semibold text-teal bg-teal/5 px-2 py-0.5 rounded">
              Status: {report?.processing_status}
            </span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold text-navy">
            {report?.report_name}
          </h1>
          <p className="text-xs text-blue-grey mt-1">
            {parameters.length} lab parameter{parameters.length === 1 ? '' : 's'} extracted from document
          </p>
        </div>

        {!analysis && (
          <button
            onClick={handleTriggerAnalysis}
            disabled={analyzing}
            className="btn-primary text-xs !py-2.5 !px-5 self-start sm:self-auto shrink-0 shadow-md"
          >
            {analyzing ? (
              <>
                <RefreshCw size={14} className="animate-spin" /> Analyzing with AI...
              </>
            ) : (
              <>
                <Sparkles size={14} /> Generate AI Explanation
              </>
            )}
          </button>
        )}
      </div>

      {/* OVERALL SUMMARY CARD */}
      {overall && (
        <div className="bg-white rounded-2xl p-6 sm:p-8 border border-slate-100 shadow-card space-y-6">
          <div className="flex items-center justify-between border-b border-slate-100 pb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-teal/10 text-teal flex items-center justify-center">
                <Brain size={20} />
              </div>
              <div>
                <h2 className="text-lg font-bold text-navy">Clinical Overview</h2>
                <p className="text-xs text-blue-grey">{overall.report_type || 'Laboratory Report'}</p>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <p className="text-sm text-navy leading-relaxed font-medium bg-slate-50/70 p-4 rounded-xl border border-slate-100">
              {overall.overall_assessment}
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <div className="p-4 rounded-xl bg-green-50/60 border border-green-200 space-y-2">
                <div className="flex items-center gap-2 text-green-800 font-bold text-xs">
                  <CheckCircle2 size={16} /> Within Reference Range ({overall.parameters_within_range?.length || 0})
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {overall.parameters_within_range?.map((p: string) => (
                    <span key={p} className="text-xs px-2 py-0.5 bg-white text-green-800 rounded font-medium border border-green-200">
                      {p}
                    </span>
                  ))}
                </div>
              </div>

              <div className="p-4 rounded-xl bg-amber-50/60 border border-amber-200 space-y-2">
                <div className="flex items-center gap-2 text-amber-800 font-bold text-xs">
                  <AlertTriangle size={16} /> Outside Reference Range ({overall.parameters_outside_range?.length || 0})
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {overall.parameters_outside_range?.map((p: string) => (
                    <span key={p} className="text-xs px-2 py-0.5 bg-white text-amber-800 rounded font-medium border border-amber-200">
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {overall.potentially_critical_flags?.length > 0 && (
              <div className="p-4 rounded-xl bg-red-50 border border-red-200 space-y-1">
                <div className="flex items-center gap-2 text-red-700 font-bold text-xs">
                  <AlertTriangle size={16} /> Potentially Critical / Urgent Parameters
                </div>
                <p className="text-xs text-red-800 leading-relaxed">
                  The following findings may warrant prompt medical attention: {overall.potentially_critical_flags.join(', ')}. Please contact your doctor or healthcare provider promptly.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* PARAMETERS SECTION */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-navy flex items-center gap-2">
            <Activity size={18} className="text-teal" /> Extracted Laboratory Parameters ({parameters.length})
          </h2>
          <span className="text-xs text-blue-grey font-medium">
            Values extracted directly from original document
          </span>
        </div>

        {parameters.length === 0 ? (
          <div className="bg-white p-8 rounded-2xl border border-slate-100 shadow-card text-center text-xs text-blue-grey">
            No extracted parameters found for this document.
          </div>
        ) : (
          <div className="space-y-4">
            {parameters.map((param) => {
              const exp = detailed[param.parameter_name];
              const isHigh = param.laboratory_flag === 'H' || exp?.classification === 'ABOVE_RANGE';
              const isLow = param.laboratory_flag === 'L' || exp?.classification === 'BELOW_RANGE';
              const isCritical = param.laboratory_flag === 'CRITICAL';
              const confPercent = Math.round((param.extraction_confidence || 0.8) * 100);
              const isEditing = editingParamId === param.id;

              return (
                <div
                  key={param.id || param.parameter_name}
                  className={`bg-white rounded-2xl p-6 border shadow-card space-y-4 transition ${
                    isCritical
                      ? 'border-red-300 ring-1 ring-red-200'
                      : param.needs_user_review
                      ? 'border-amber-300 bg-amber-50/20'
                      : 'border-slate-100 hover:border-slate-200'
                  }`}
                >
                  {/* Critical Safety Notice if applicable */}
                  {isCritical && (
                    <div className="p-3 bg-red-100 border border-red-200 rounded-xl flex items-start gap-2.5 text-xs text-red-800 font-medium">
                      <AlertTriangle size={16} className="text-red-600 shrink-0 mt-0.5" />
                      <span>
                        <strong>Safety Notice:</strong> This parameter represents a potentially critical physiological value. Please review this promptly with your doctor or clinical provider.
                      </span>
                    </div>
                  )}

                  {/* Header Row */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-bold text-base text-navy">
                          {param.parameter_name}
                        </h3>

                        {/* Extraction Confidence Badge */}
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            confPercent >= 85
                              ? 'bg-green-100 text-green-800'
                              : confPercent >= 70
                              ? 'bg-teal/10 text-teal-dark'
                              : 'bg-amber-100 text-amber-800'
                          }`}
                        >
                          {confPercent}% Confidence
                        </span>

                        {param.user_confirmed && (
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 flex items-center gap-1">
                            <CheckCheck size={11} /> Verified by Patient
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                        {isEditing ? (
                          <div className="flex items-center gap-2 mt-1">
                            <input
                              type="text"
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              placeholder="Value"
                              className="px-2 py-1 border border-slate-300 rounded text-sm w-24 font-bold text-navy"
                            />
                            <input
                              type="text"
                              value={editUnit}
                              onChange={(e) => setEditUnit(e.target.value)}
                              placeholder="Unit"
                              className="px-2 py-1 border border-slate-300 rounded text-xs w-20 text-blue-grey"
                            />
                            <button
                              onClick={() => handleConfirmParameter(param.id)}
                              disabled={confirming}
                              className="btn-primary !py-1 !px-2.5 text-xs inline-flex items-center gap-1"
                            >
                              <Check size={12} /> Save
                            </button>
                            <button
                              onClick={() => setEditingParamId(null)}
                              className="text-xs text-slate-400 hover:text-navy px-2"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <>
                            <span className="text-xl font-extrabold text-navy">
                              {param.observed_value}
                            </span>
                            {param.unit && (
                              <span className="text-xs font-semibold text-blue-grey bg-slate-100 px-2 py-0.5 rounded">
                                {param.unit}
                              </span>
                            )}
                            <span className="text-xs text-slate-400">
                              Reference: {param.reference_text || 'Standard Range Not Reported by Lab'}
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2.5 self-start sm:self-center shrink-0">
                      {param.needs_user_review && !isEditing && (
                        <button
                          onClick={() => {
                            setEditingParamId(param.id);
                            setEditValue(param.observed_value);
                            setEditUnit(param.unit || '');
                          }}
                          className="px-2.5 py-1 bg-amber-100 hover:bg-amber-200 text-amber-800 text-xs font-semibold rounded-lg inline-flex items-center gap-1.5 transition"
                        >
                          <Edit2 size={12} /> Confirm / Adjust
                        </button>
                      )}

                      <span
                        className={`text-xs font-bold px-3 py-1 rounded-full ${
                          isCritical
                            ? 'bg-red-100 text-red-700'
                            : isHigh
                            ? 'bg-amber-100 text-amber-800'
                            : isLow
                            ? 'bg-blue-100 text-blue-800'
                            : 'bg-green-100 text-green-700'
                        }`}
                      >
                        {isCritical
                          ? 'Critical Flag'
                          : isHigh
                          ? 'Above Range'
                          : isLow
                          ? 'Below Range'
                          : 'Within Range'}
                      </span>
                    </div>
                  </div>

                  {exp ? (
                    <div className="pt-3 border-t border-slate-100 space-y-3 text-xs leading-relaxed">
                      {exp.what_it_measures && (
                        <div>
                          <span className="font-bold text-navy">What this test measures: </span>
                          <span className="text-blue-grey">{exp.what_it_measures}</span>
                        </div>
                      )}
                      {exp.simple_explanation && (
                        <div>
                          <span className="font-bold text-navy">Result explanation: </span>
                          <span className="text-blue-grey">{exp.simple_explanation}</span>
                        </div>
                      )}
                      {exp.when_to_seek_attention && (
                        <div className="p-3 bg-slate-50 rounded-lg text-slate-700">
                          <span className="font-semibold text-navy">Guidance: </span>
                          {exp.when_to_seek_attention}
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400 italic pt-2 border-t border-slate-50">
                      Detailed AI explanation not yet generated. Click &quot;Generate AI Explanation&quot; above to view plain-language insights.
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* DOCTOR DISCUSSION QUESTIONS SECTION */}
      {questions.length > 0 && (
        <div className="bg-white rounded-2xl p-6 sm:p-8 border border-slate-100 shadow-card space-y-6">
          <div className="flex items-center justify-between border-b border-slate-100 pb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-teal/10 text-teal flex items-center justify-center">
                <MessageSquare size={20} />
              </div>
              <div>
                <h2 className="text-lg font-bold text-navy">Questions for Your Doctor</h2>
                <p className="text-xs text-blue-grey">Personalized questions generated from your test values</p>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            {questions.map((q) => {
              const isDiscussed = q.discussion_status === 'DISCUSSED';
              return (
                <div
                  key={q.id}
                  className={`p-4 rounded-xl border transition flex items-start justify-between gap-4 ${
                    isDiscussed
                      ? 'bg-slate-50/60 border-slate-200 opacity-75'
                      : 'bg-white border-slate-200 hover:border-teal/40 shadow-xs'
                  }`}
                >
                  <div className="space-y-1">
                    <p className={`text-sm font-medium ${isDiscussed ? 'line-through text-slate-400' : 'text-navy'}`}>
                      {q.question}
                    </p>
                    <span className="inline-block text-[10px] uppercase font-bold text-slate-400">
                      Status: {q.discussion_status}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => handleCopyQuestion(q.question, q.id)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-navy hover:bg-slate-100 transition"
                      title="Copy Question"
                    >
                      {copiedId === q.id ? <Check size={16} className="text-teal" /> : <Copy size={16} />}
                    </button>
                    <button
                      onClick={() => handleToggleQuestionStatus(q.id, q.discussion_status)}
                      className={`text-xs font-semibold px-2.5 py-1 rounded-lg transition ${
                        isDiscussed
                          ? 'bg-slate-200 text-slate-600 hover:bg-slate-300'
                          : 'bg-teal/10 text-teal-dark hover:bg-teal/20'
                      }`}
                    >
                      {isDiscussed ? 'Mark Pending' : 'Mark Discussed'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Raw Extracted Text Modal */}
      {showRawText && (
        <div className="fixed inset-0 z-50 bg-navy/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white w-full max-w-2xl rounded-2xl overflow-hidden shadow-2xl border border-slate-100 flex flex-col max-h-[80vh]">
            <div className="p-4 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText size={18} className="text-teal" />
                <h3 className="font-bold text-sm text-navy">Preserved Raw Extracted Document Text</h3>
              </div>
              <button
                onClick={() => setShowRawText(false)}
                className="text-slate-400 hover:text-navy p-1 rounded-lg"
              >
                <X size={20} />
              </button>
            </div>
            <div className="p-4 overflow-y-auto font-mono text-xs text-slate-800 bg-slate-50 whitespace-pre-wrap leading-relaxed select-all">
              {rawText || 'No raw text preserved for this document.'}
            </div>
            <div className="p-3 bg-slate-100 border-t border-slate-200 flex items-center justify-between">
              <span className="text-[11px] text-blue-grey">
                Exact unmodified output from document text recognition engine
              </span>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(rawText);
                  toast.success('Raw text copied to clipboard');
                }}
                className="btn-outline !py-1 !px-3 text-xs inline-flex items-center gap-1.5"
              >
                <Copy size={12} /> Copy Text
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Mandatory Medical Disclaimer Banner */}
      <div className="p-5 rounded-2xl bg-amber-50 border border-amber-200 flex items-start gap-3">
        <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
        <div className="text-xs text-amber-900 leading-relaxed">
          <strong>Mandatory Medical Notice:</strong> The insights and explanations provided above are generated automatically by artificial intelligence for informational purposes only. They do not constitute a medical diagnosis, clinical evaluation, or treatment recommendation. Individual laboratory reference ranges may vary. Always discuss these findings directly with your physician or healthcare provider.
        </div>
      </div>
    </div>
  );
}

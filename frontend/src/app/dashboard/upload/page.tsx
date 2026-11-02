'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useDropzone } from 'react-dropzone';
import { 
  Camera, FileText, AlertCircle, 
  X, ArrowRight, Shield, RefreshCw, FileUp, Info,
  CheckCircle2, RotateCcw, Ban, SwitchCamera, Eye
} from 'lucide-react';
import { createClient } from '@/lib/supabase/client';
import { toast } from 'sonner';

const MAX_SIZE_MB = 20;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;
const ALLOWED_TYPES = {
  'application/pdf': ['.pdf'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
};

export default function UploadReportPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [reportName, setReportName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusStep, setStatusStep] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Live Camera Viewfinder State
  const [showCameraModal, setShowCameraModal] = useState(false);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [facingMode, setFacingMode] = useState<'user' | 'environment'>('environment');
  const [cameraError, setCameraError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  // Abort controller for cancellation
  const abortControllerRef = useRef<AbortController | null>(null);

  // Revoke preview URL on unmount or file change
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  // Handle setting file and generating preview
  const handleSelectFile = useCallback((selected: File) => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setFile(selected);
    setErrorMsg(null);
    const objectUrl = URL.createObjectURL(selected);
    setPreviewUrl(objectUrl);
    if (!reportName) {
      const cleanTitle = selected.name.replace(/\.[^/.]+$/, '').replace(/[_-]/g, ' ');
      setReportName(cleanTitle.charAt(0).toUpperCase() + cleanTitle.slice(1));
    }
  }, [previewUrl, reportName]);

  // Dropzone setup
  const onDrop = useCallback((acceptedFiles: File[], rejectedFiles: any[]) => {
    setErrorMsg(null);

    if (rejectedFiles.length > 0) {
      const rejection = rejectedFiles[0];
      if (rejection.file.size > MAX_SIZE_BYTES) {
        setErrorMsg(`File size exceeds the ${MAX_SIZE_MB}MB limit. Please upload a smaller file.`);
        toast.error(`File size exceeds ${MAX_SIZE_MB}MB.`);
      } else {
        setErrorMsg('Invalid file format. Only PDF, JPG, and PNG medical reports are supported.');
        toast.error('Unsupported file format.');
      }
      return;
    }

    if (acceptedFiles.length > 0) {
      handleSelectFile(acceptedFiles[0]);
    }
  }, [handleSelectFile]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ALLOWED_TYPES,
    maxSize: MAX_SIZE_BYTES,
    multiple: false,
  });

  // Mobile camera fallback
  const handleMobileCameraCapture = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const captured = e.target.files[0];
      if (captured.size > MAX_SIZE_BYTES) {
        setErrorMsg(`Photo size exceeds ${MAX_SIZE_MB}MB limit.`);
        return;
      }
      handleSelectFile(captured);
    }
  };

  // Live Camera Modal Helpers
  const startCamera = async (mode: 'user' | 'environment') => {
    setCameraError(null);
    try {
      if (cameraStream) {
        cameraStream.getTracks().forEach((track) => track.stop());
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: mode, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
      setCameraStream(stream);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch (err: any) {
      console.error('Camera access error:', err);
      setCameraError('Could not access camera. Please check camera permissions in your browser or use file upload.');
    }
  };

  const openCameraModal = () => {
    setShowCameraModal(true);
    startCamera(facingMode);
  };

  const closeCameraModal = () => {
    if (cameraStream) {
      cameraStream.getTracks().forEach((track) => track.stop());
      setCameraStream(null);
    }
    setShowCameraModal(false);
  };

  const toggleCameraFacingMode = () => {
    const nextMode = facingMode === 'environment' ? 'user' : 'environment';
    setFacingMode(nextMode);
    startCamera(nextMode);
  };

  const capturePhoto = () => {
    if (!videoRef.current) return;
    const video = videoRef.current;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const capturedFile = new File(
          [blob],
          `camera_scan_${Date.now()}.jpg`,
          { type: 'image/jpeg' }
        );
        handleSelectFile(capturedFile);
        closeCameraModal();
        toast.success('Document scan captured successfully!');
      },
      'image/jpeg',
      0.95
    );
  };

  // Upload Cancellation
  const handleCancelUpload = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setUploading(false);
    setProgress(0);
    setStatusStep('');
    setErrorMsg('Upload was cancelled.');
    toast.info('Upload cancelled.');
  };

  // Upload Submission
  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!file) {
      setErrorMsg('Please select a report file or take a photo first.');
      return;
    }

    setUploading(true);
    setErrorMsg(null);
    setProgress(15);
    setStatusStep('Step 1 of 3: Validating file structure and integrity...');

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();

      if (!session?.access_token) {
        setErrorMsg('Authentication session not found. Please log in again.');
        toast.error('Session expired. Please log in.');
        return;
      }

      const backendUrl = (process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
      const formData = new FormData();
      formData.append('file', file);
      formData.append('report_name', reportName.trim() || file.name);

      setProgress(45);
      setStatusStep('Step 2 of 3: Encrypting and saving to private medical storage...');

      const headers: Record<string, string> = {
        Authorization: `Bearer ${session.access_token}`,
      };

      const res = await fetch(`${backendUrl}/api/v1/reports/upload`, {
        method: 'POST',
        headers,
        body: formData,
        signal: abortController.signal,
      });

      setProgress(80);
      setStatusStep('Step 3 of 3: Running OCR text and lab parameter extraction...');

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: 'Upload failed' }));
        throw new Error(errorData.detail || `Upload failed with status ${res.status}`);
      }

      const data = await res.json();

      if (!data?.report_id) {
        throw new Error('Upload succeeded but no report ID was returned. Please check your report history.');
      }

      setProgress(100);
      setStatusStep('Extraction complete! Redirecting to report overview...');

      toast.success('Medical report uploaded and parsed successfully!');
      router.push(`/dashboard/report/${data.report_id}`);
    } catch (err: any) {
      if (err.name === 'AbortError') {
        // Already handled in handleCancelUpload
        return;
      }
      console.error('Upload error:', err);
      const isNetworkError = err.message === 'Failed to fetch' || err instanceof TypeError;
      const displayError = isNetworkError
        ? 'Connection failed: Unable to communicate with the backend server (Failed to fetch). Please check backend CORS settings or verify the service is active.'
        : (err.message || 'An error occurred during file upload. Please verify your connection.');
      setErrorMsg(displayError);
      toast.error(displayError);
    } finally {
      abortControllerRef.current = null;
      setUploading(false);
    }
  };

  const clearSelectedFile = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setFile(null);
    setPreviewUrl(null);
    setReportName('');
    setErrorMsg(null);
    setProgress(0);
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Title */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-navy">
          Upload Medical Report
        </h1>
        <p className="text-sm text-blue-grey mt-1">
          Upload a lab test document (PDF, JPG, PNG) or scan physical paperwork using your camera.
        </p>
      </div>

      {/* Error Alert with Retry */}
      {errorMsg && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700 font-medium">{errorMsg}</p>
          </div>
          {file && !uploading && (
            <button
              type="button"
              onClick={() => handleSubmit()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-red-100 hover:bg-red-200 text-red-800 text-xs font-semibold rounded-lg transition shrink-0"
            >
              <RotateCcw size={14} /> Retry Upload
            </button>
          )}
        </div>
      )}

      {/* Main Upload / Preview Area */}
      <div className="space-y-6">
        {!file ? (
          <div className="space-y-4">
            {/* Drag & Drop Zone */}
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center cursor-pointer transition ${
                isDragActive
                  ? 'border-teal bg-teal/5'
                  : 'border-slate-200 hover:border-teal/50 hover:bg-slate-50/50 bg-white'
              }`}
            >
              <input {...getInputProps()} />
              <div className="w-16 h-16 rounded-2xl bg-teal/10 text-teal flex items-center justify-center mx-auto mb-4">
                <FileUp size={30} />
              </div>
              <h3 className="text-base font-bold text-navy mb-1">
                {isDragActive ? 'Drop your report file here' : 'Drag & drop your medical report here'}
              </h3>
              <p className="text-xs text-blue-grey mb-4">
                Supports PDF, JPG, and PNG files up to 20MB
              </p>
              <button
                type="button"
                className="btn-primary text-xs !py-2 !px-4 pointer-events-none"
              >
                Browse Files
              </button>
            </div>

            {/* Camera Options */}
            <div className="flex items-center justify-center">
              <span className="text-xs text-slate-400 uppercase font-semibold px-3">or capture with camera</span>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-3">
              {/* Desktop/Tablet interactive viewfinder */}
              <button
                type="button"
                onClick={openCameraModal}
                className="btn-outline text-xs !py-2.5 !px-5 inline-flex items-center gap-2"
              >
                <Camera size={16} /> Open Camera Scanner
              </button>

              {/* Native mobile camera fallback */}
              <input
                ref={cameraInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={handleMobileCameraCapture}
              />
              <button
                type="button"
                onClick={() => cameraInputRef.current?.click()}
                className="text-xs text-blue-grey hover:text-navy underline p-2 sm:hidden"
              >
                Use native mobile camera
              </button>
            </div>
          </div>
        ) : (
          /* File Preview Card */
          <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-card space-y-6">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-4">
                {/* Thumbnail Preview for Images / Icon for PDF */}
                {file.type.startsWith('image/') && previewUrl ? (
                  <div className="w-16 h-16 rounded-xl overflow-hidden border border-slate-200 bg-slate-50 shrink-0 relative group">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={previewUrl}
                      alt="Report preview"
                      className="w-full h-full object-cover"
                    />
                  </div>
                ) : (
                  <div className="w-16 h-16 rounded-xl bg-teal/10 text-teal flex items-center justify-center shrink-0">
                    <FileText size={32} />
                  </div>
                )}

                <div>
                  <h4 className="font-semibold text-base text-navy break-all">{file.name}</h4>
                  <p className="text-xs text-blue-grey mt-0.5">
                    {(file.size / (1024 * 1024)).toFixed(2)} MB · {file.type.toUpperCase() || 'DOCUMENT'}
                  </p>
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-teal mt-1">
                    <CheckCircle2 size={13} /> Ready for upload
                  </span>
                </div>
              </div>

              {!uploading && (
                <button
                  type="button"
                  onClick={clearSelectedFile}
                  title="Remove document and select another"
                  className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition"
                >
                  <X size={20} />
                </button>
              )}
            </div>

            {/* Embedded PDF / Full Image Preview Accordion */}
            {previewUrl && (
              <div className="border border-slate-200 rounded-xl overflow-hidden bg-slate-50">
                <div className="p-3 bg-slate-100 border-b border-slate-200 flex items-center justify-between text-xs font-semibold text-navy">
                  <span className="flex items-center gap-1.5">
                    <Eye size={14} className="text-teal" /> Pre-Upload Document Preview
                  </span>
                  <span className="text-[11px] text-blue-grey font-normal">
                    {file.type.includes('pdf') ? 'PDF Document' : 'High-Resolution Scan'}
                  </span>
                </div>
                <div className="p-4 flex items-center justify-center max-h-80 overflow-y-auto">
                  {file.type.startsWith('image/') ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                      src={previewUrl}
                      alt="Full document preview"
                      className="max-h-72 object-contain rounded-lg border border-slate-200 shadow-sm"
                    />
                  ) : (
                    <div className="w-full py-8 text-center space-y-2">
                      <FileText size={48} className="mx-auto text-teal" />
                      <p className="text-sm font-semibold text-navy">{file.name}</p>
                      <p className="text-xs text-blue-grey">
                        PDF validated ({ (file.size / (1024 * 1024)).toFixed(2) } MB). PyMuPDF will extract all lab test tables upon upload.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Report Label Input */}
            <div>
              <label className="block text-xs font-semibold text-navy mb-1.5">
                Report Title / Clinical Context
              </label>
              <input
                type="text"
                value={reportName}
                onChange={(e) => setReportName(e.target.value)}
                placeholder="e.g. Complete Blood Count - May 2026"
                disabled={uploading}
                className="block w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm text-navy placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal"
              />
              <p className="text-[11px] text-blue-grey mt-1">
                A descriptive title helps you track your parameters in report history.
              </p>
            </div>

            {/* Upload Progress Bar & Status */}
            {uploading && (
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-teal flex items-center gap-2">
                    <RefreshCw size={14} className="animate-spin" /> {statusStep}
                  </span>
                  <span className="font-bold text-navy">{progress}%</span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden">
                  <div
                    className="bg-teal h-2.5 rounded-full transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <div className="flex justify-end pt-1">
                  <button
                    type="button"
                    onClick={handleCancelUpload}
                    className="inline-flex items-center gap-1.5 text-xs text-red-600 hover:text-red-700 font-semibold px-2 py-1 rounded hover:bg-red-50 transition"
                  >
                    <Ban size={14} /> Cancel Upload
                  </button>
                </div>
              </div>
            )}

            {/* Action Buttons */}
            {!uploading && (
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
                <button
                  type="button"
                  onClick={clearSelectedFile}
                  className="w-full sm:w-auto px-4 py-2.5 rounded-xl border border-slate-200 text-xs font-semibold text-blue-grey hover:bg-slate-50 transition"
                >
                  Change File
                </button>
                <button
                  type="button"
                  onClick={() => handleSubmit()}
                  className="w-full sm:w-auto btn-primary justify-center text-sm py-2.5 px-6"
                >
                  Confirm & Upload Report <ArrowRight size={16} />
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Live Camera Viewfinder Modal */}
      {showCameraModal && (
        <div className="fixed inset-0 z-50 bg-navy/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white w-full max-w-lg rounded-2xl overflow-hidden shadow-2xl border border-slate-100 flex flex-col">
            <div className="p-4 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Camera size={18} className="text-teal" />
                <h3 className="font-bold text-sm text-navy">Scan Medical Report</h3>
              </div>
              <button
                type="button"
                onClick={closeCameraModal}
                className="text-slate-400 hover:text-navy p-1 rounded-lg"
              >
                <X size={20} />
              </button>
            </div>

            <div className="relative bg-black min-h-[320px] max-h-[460px] flex items-center justify-center overflow-hidden">
              {cameraError ? (
                <div className="p-6 text-center text-white space-y-2">
                  <AlertCircle size={32} className="mx-auto text-red-400" />
                  <p className="text-xs text-slate-300">{cameraError}</p>
                </div>
              ) : (
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  className="w-full h-full object-cover"
                />
              )}
            </div>

            <div className="p-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={toggleCameraFacingMode}
                className="p-2.5 rounded-xl border border-slate-200 text-blue-grey hover:text-navy hover:bg-white text-xs inline-flex items-center gap-1.5 transition"
                title="Switch front/rear camera"
              >
                <SwitchCamera size={16} /> Flip Camera
              </button>

              <button
                type="button"
                onClick={capturePhoto}
                disabled={!!cameraError}
                className="btn-primary !py-2.5 !px-6 text-xs inline-flex items-center gap-2 shadow-md disabled:opacity-50"
              >
                <Camera size={16} /> Capture Document
              </button>

              <button
                type="button"
                onClick={closeCameraModal}
                className="p-2.5 rounded-xl text-blue-grey hover:text-navy text-xs"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Security & Data Protection Box */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5 space-y-3">
        <div className="flex items-center gap-2 text-navy font-bold text-sm">
          <Shield size={16} className="text-teal" /> Medical Data Protection Guarantee
        </div>
        <p className="text-xs text-blue-grey leading-relaxed">
          Your medical records are stored in a private Supabase Storage bucket protected by database-enforced Row Level Security (RLS). No public URLs are ever created. Documents are accessed only via short-lived, encrypted signed URLs valid for 60 minutes.
        </p>
        <div className="flex items-start gap-2 pt-2 text-[11px] text-slate-500">
          <Info size={14} className="shrink-0 mt-0.5 text-blue-grey" />
          <span>
            MediExplain AI provides factual explanations of lab parameters to empower your clinical discussions. It does not provide medical diagnoses or prescribe medications.
          </span>
        </div>
      </div>
    </div>
  );
}

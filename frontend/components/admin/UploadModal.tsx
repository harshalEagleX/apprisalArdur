"use client";
import { useState, useRef, useEffect } from "react";
import { AlertCircle, CheckCircle2, X, Upload } from "lucide-react";
import { getClients, uploadBatch, type Client } from "@/lib/api";
import Spinner from "@/components/shared/Spinner";

interface Props {
  open: boolean;
  onClose: () => void;
  onUploaded: (batchId: number, batchRef: string, fileCount: number) => void;
}

export default function UploadModal({ open, onClose, onUploaded }: Props) {
  const [clients, setClients]     = useState<Client[]>([]);
  const [clientId, setClientId]   = useState<number | "">("");
  const [file, setFile]           = useState<File | null>(null);
  const [dragging, setDragging]   = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress]   = useState(0);
  const [error, setError]         = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ client?: string; file?: string }>({});
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const timer = window.setTimeout(() => {
      setFile(null); setClientId(""); setError(""); setFieldErrors({}); setProgress(0);
      getClients().then(setClients).catch(() => null);
      dialogRef.current?.focus();
    }, 0);
    return () => {
      window.clearTimeout(timer);
      previousFocusRef.current?.focus();
    };
  }, [open]);

  if (!open) return null;

  function handleDrop(e: React.DragEvent) {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    acceptFile(f);
  }

  function acceptFile(f?: File) {
    if (!f) return;
    const nextErrors: typeof fieldErrors = {};
    if (!f.name.toLowerCase().endsWith(".zip")) {
      nextErrors.file = "Only ZIP archives are accepted.";
    } else if (f.size > 50 * 1024 * 1024) {
      nextErrors.file = "ZIP file must be 50 MB or smaller.";
    }
    setFieldErrors(prev => ({ ...prev, file: nextErrors.file }));
    if (!nextErrors.file) {
      setFile(f);
      setError("");
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const nextErrors: typeof fieldErrors = {};
    if (!clientId) nextErrors.client = "Select the client organisation for this batch.";
    if (!file) nextErrors.file = "Select a ZIP archive before uploading.";
    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      setError("Fix the highlighted fields before uploading.");
      return;
    }
    const selectedFile = file;
    if (!selectedFile) return;
    setError(""); setUploading(true); setProgress(0);

    // Simulate upload progress while we wait for the server
    const interval = setInterval(() => setProgress(p => Math.min(p + 8, 85)), 300);
    try {
      const result = await uploadBatch(selectedFile, clientId as number);
      clearInterval(interval); setProgress(100);
      await new Promise(r => setTimeout(r, 400));
      onUploaded(result.batchId, result.parentBatchId, result.fileCount);
      onClose();
    } catch (err: unknown) {
      clearInterval(interval); setProgress(0);
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function handleDialogKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape" && !uploading) {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key !== "Tab") return;
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable || focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  function openFilePicker() {
    if (!uploading) inputRef.current?.click();
  }

  function handleDropzoneKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openFilePicker();
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={!uploading ? onClose : undefined} />
      <div
        ref={dialogRef}
        className="relative mx-4 w-full max-w-lg rounded-lg border border-slate-700 bg-slate-900 shadow-2xl focus:outline-none"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-dialog-title"
        aria-describedby="upload-dialog-description"
        tabIndex={-1}
        onKeyDown={handleDialogKeyDown}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <div>
            <h2 id="upload-dialog-title" className="text-sm font-semibold text-white">Upload batch</h2>
            <p id="upload-dialog-description" className="text-[11px] text-slate-500 mt-0.5">ZIP must contain appraisal and engagement folders. Contracts are optional.</p>
          </div>
          {!uploading && (
            <button onClick={onClose} className="rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-300" aria-label="Close upload dialog">
              <X size={16} />
            </button>
          )}
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-800 bg-red-950/60 px-3 py-2.5 text-xs text-red-300">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Client selector */}
          <section className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <div className="mb-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Batch owner</h3>
              <p className="mt-0.5 text-[11px] text-slate-600">This controls storage paths and client-level reporting.</p>
            </div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Client organisation <span className="text-red-400">*</span></label>
            <select value={clientId} onChange={e => setClientId(e.target.value ? Number(e.target.value) : "")}
              disabled={uploading || clients.length === 0} className={`${INPUT} ${fieldErrors.client ? "border-red-700 focus:ring-red-500" : ""}`}>
              <option value="">{clients.length === 0 ? "No clients available" : "Select client..."}</option>
              {clients.map(c => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}
            </select>
            {fieldErrors.client && <FieldError>{fieldErrors.client}</FieldError>}
          </section>

          {/* Drop zone */}
          <section className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <div className="mb-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Archive</h3>
              <p className="mt-0.5 text-[11px] text-slate-600">Maximum 50 MB. The backend validates the folder structure after upload.</p>
            </div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">ZIP archive <span className="text-red-400">*</span></label>
            <div
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={openFilePicker}
              onKeyDown={handleDropzoneKeyDown}
              role="button"
              tabIndex={uploading ? -1 : 0}
              aria-label={file ? `Selected ZIP archive ${file.name}. Press Enter to choose a different file.` : "Choose ZIP archive"}
              className={`border-2 border-dashed rounded-xl p-6 text-center transition-colors ${
                uploading ? "cursor-not-allowed opacity-60 border-slate-700" :
                dragging ? "border-blue-500 bg-blue-950/30 cursor-copy" :
                file ? "border-green-700 bg-green-950/20 cursor-pointer" :
                fieldErrors.file ? "border-red-700 bg-red-950/10 cursor-pointer" :
                "border-slate-700 hover:border-slate-600 cursor-pointer"
              }`}
            >
              <input ref={inputRef} type="file" accept=".zip" className="hidden"
                onChange={e => acceptFile(e.target.files?.[0])} />
              {file ? (
                <div className="flex flex-col items-center gap-1.5">
                  <CheckCircle2 size={22} className="text-green-400" />
                  <span className="text-sm font-medium text-green-300">{file.name}</span>
                  <span className="text-xs text-slate-500">{(file.size / 1024 / 1024).toFixed(1)} MB</span>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-1.5">
                  <Upload size={20} className="text-slate-500" />
                  <span className="text-sm text-slate-400">Drop ZIP here or click to browse</span>
                  <span className="text-xs text-slate-600">Maximum 50 MB</span>
                </div>
              )}
            </div>
            {fieldErrors.file && <FieldError>{fieldErrors.file}</FieldError>}
          </section>

          {/* Upload progress bar */}
          {uploading && (
            <div>
              <div className="flex justify-between text-xs text-slate-400 mb-1.5">
                <span>Uploading and validating…</span>
                <span className="font-mono">{progress}%</span>
              </div>
              <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}

          <div className="flex gap-2 justify-end pt-1">
            {!uploading && (
              <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium transition-colors">
                Cancel
              </button>
            )}
            <button type="submit" disabled={uploading || !file || !clientId}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium transition-colors flex items-center gap-2">
              {uploading && <Spinner size={13} />}
              {uploading ? "Uploading…" : "Upload batch"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const INPUT = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-colors disabled:opacity-50";

function FieldError({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-red-300">
      <AlertCircle size={11} />
      <span>{children}</span>
    </div>
  );
}

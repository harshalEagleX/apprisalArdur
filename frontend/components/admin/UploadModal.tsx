"use client";
import { useState, useRef, useEffect } from "react";
import { X, Upload, FileArchive } from "lucide-react";
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
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => {
      setFile(null); setClientId(""); setError(""); setProgress(0);
      getClients().then(setClients).catch(() => null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [open]);

  if (!open) return null;

  function handleDrop(e: React.DragEvent) {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f?.name.endsWith(".zip")) { setFile(f); setError(""); }
    else setError("Only ZIP archives are accepted");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setError("Select a ZIP file"); return; }
    if (!clientId) { setError("Select a client organisation"); return; }
    setError(""); setUploading(true); setProgress(0);

    // Simulate upload progress while we wait for the server
    const interval = setInterval(() => setProgress(p => Math.min(p + 8, 85)), 300);
    try {
      const result = await uploadBatch(file, clientId as number);
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={!uploading ? onClose : undefined} />
      <div className="relative bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md mx-4 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <div>
            <h2 className="text-sm font-semibold text-white">Upload batch</h2>
            <p className="text-[11px] text-slate-500 mt-0.5">ZIP must contain <code className="bg-slate-800 px-1 rounded">appraisal/</code> and <code className="bg-slate-800 px-1 rounded">engagement/</code> folders</p>
          </div>
          {!uploading && (
            <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
              <X size={16} />
            </button>
          )}
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="text-xs text-red-300 bg-red-950/60 border border-red-800 rounded-lg px-3 py-2.5">{error}</div>
          )}

          {/* Client selector */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Client organisation <span className="text-red-400">*</span></label>
            <select value={clientId} onChange={e => setClientId(e.target.value ? Number(e.target.value) : "")}
              disabled={uploading} className={INPUT}>
              <option value="">Select client…</option>
              {clients.map(c => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}
            </select>
          </div>

          {/* Drop zone */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">ZIP archive <span className="text-red-400">*</span></label>
            <div
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => !uploading && inputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-6 text-center transition-colors ${
                uploading ? "cursor-not-allowed opacity-60 border-slate-700" :
                dragging ? "border-blue-500 bg-blue-950/30 cursor-copy" :
                file ? "border-green-700 bg-green-950/20 cursor-pointer" :
                "border-slate-700 hover:border-slate-600 cursor-pointer"
              }`}
            >
              <input ref={inputRef} type="file" accept=".zip" className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) { setFile(f); setError(""); }}} />
              {file ? (
                <div className="flex flex-col items-center gap-1.5">
                  <FileArchive size={22} className="text-green-400" />
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
          </div>

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

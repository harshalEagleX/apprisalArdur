"use client";
import { useState, useRef } from "react";
import { getClients, uploadBatch, type Client } from "@/lib/api";
import { useEffect } from "react";

interface UploadModalProps {
  open: boolean;
  onClose: () => void;
  onUploaded: (batchId: number) => void;
}

export default function UploadModal({ open, onClose, onUploaded }: UploadModalProps) {
  const [clients, setClients]     = useState<Client[]>([]);
  const [clientId, setClientId]   = useState<number | "">("");
  const [file, setFile]           = useState<File | null>(null);
  const [dragging, setDragging]   = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError]         = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setFile(null); setClientId(""); setError("");
    getClients().then(setClients).catch(() => null);
  }, [open]);

  if (!open) return null;

  function handleDrop(e: React.DragEvent) {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f?.name.endsWith(".zip")) setFile(f);
    else setError("Only ZIP files are accepted");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setError("Please select a ZIP file"); return; }
    if (!clientId) { setError("Please select a client organisation"); return; }
    setError(""); setUploading(true);
    try {
      const result = await uploadBatch(file, clientId as number);
      onUploaded(result.batchId);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-md mx-4 shadow-2xl">
        <h3 className="text-lg font-semibold text-white mb-4">Upload Batch</h3>
        <p className="text-slate-400 text-sm mb-4">
          Upload a ZIP archive containing <code className="bg-slate-800 px-1 rounded">appraisal/</code> and{" "}
          <code className="bg-slate-800 px-1 rounded">engagement/</code> folders.
        </p>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-900/40 border border-red-700 text-red-300 text-sm">{error}</div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Client selector */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Client Organisation <span className="text-red-400">*</span>
            </label>
            <select value={clientId} onChange={e => setClientId(e.target.value ? Number(e.target.value) : "")}
              className={INPUT}>
              <option value="">— Select client —</option>
              {clients.map(c => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}
            </select>
          </div>

          {/* Drop zone */}
          <div
            onDragOver={e => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
              dragging ? "border-blue-500 bg-blue-500/10" :
              file ? "border-green-600 bg-green-900/10" :
              "border-slate-700 hover:border-slate-600"
            }`}
          >
            <input ref={inputRef} type="file" accept=".zip" className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) setFile(f); }} />
            {file ? (
              <>
                <div className="text-green-400 text-2xl mb-1">✓</div>
                <div className="text-green-300 text-sm font-medium">{file.name}</div>
                <div className="text-slate-500 text-xs">{(file.size / 1024 / 1024).toFixed(1)} MB</div>
              </>
            ) : (
              <>
                <div className="text-slate-400 text-2xl mb-1">📦</div>
                <div className="text-slate-300 text-sm font-medium">Drop ZIP here or click to browse</div>
                <div className="text-slate-500 text-xs mt-0.5">Max 50 MB</div>
              </>
            )}
          </div>

          <div className="flex gap-3 justify-end pt-1">
            <button type="button" onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 text-sm font-medium transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={uploading || !file}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium transition-colors">
              {uploading ? "Uploading…" : "Upload Batch"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const INPUT = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

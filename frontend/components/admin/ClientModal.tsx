"use client";
import { useState } from "react";
import { AlertCircle, X } from "lucide-react";
import { createClient } from "@/lib/api";
import Spinner from "@/components/shared/Spinner";

interface Props { open: boolean; onClose: () => void; onSaved: () => void; }

export default function ClientModal({ open, onClose, onSaved }: Props) {
  const [name, setName]     = useState("");
  const [code, setCode]     = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ name?: string; code?: string }>({});

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const nextErrors: typeof fieldErrors = {};
    if (!name.trim()) nextErrors.name = "Organisation name is required.";
    if (!code.trim()) nextErrors.code = "Short code is required.";
    if (code && !/^[A-Z0-9_-]{2,10}$/.test(code.trim().toUpperCase())) {
      nextErrors.code = "Use 2-10 characters: A-Z, numbers, dash, or underscore.";
    }
    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      setError("Fix the highlighted fields before creating the client.");
      return;
    }
    setSaving(true);
    try {
      await createClient(name.trim(), code.trim().toUpperCase());
      setName(""); setCode("");
      onSaved(); onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create client");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative mx-4 w-full max-w-md rounded-lg border border-white/10 bg-[#11161C] shadow-[0_22px_60px_rgba(0,0,0,0.46)]">
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-white">New client organisation</h2>
            <p className="mt-0.5 text-[11px] text-slate-500">Create the tenant used for uploads, reviewers, and reporting.</p>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-slate-500 transition-colors hover:bg-white/[0.04] hover:text-slate-300" aria-label="Close client dialog">
            <X size={16} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-500/25 bg-red-950/45 px-3 py-2.5 text-xs text-red-200">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <section className="rounded-lg border border-white/10 bg-[#0B0F14]/50 p-3">
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Organisation name <span className="text-red-400">*</span></label>
            <input value={name} onChange={e => setName(e.target.value)} required
              placeholder="Acme Lending" className={inputClass(fieldErrors.name)} />
            {fieldErrors.name && <FieldError>{fieldErrors.name}</FieldError>}
          </section>
          <section className="rounded-lg border border-white/10 bg-[#0B0F14]/50 p-3">
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Short code <span className="text-red-400">*</span></label>
            <input value={code} onChange={e => setCode(e.target.value.toUpperCase())} required
              placeholder="ACME" maxLength={10} className={inputClass(fieldErrors.code)} />
            <p className="text-[11px] text-slate-600 mt-1">2-10 chars. Used in file storage paths and batch cleanup.</p>
            {fieldErrors.code && <FieldError>{fieldErrors.code}</FieldError>}
          </section>
          <div className="flex gap-2 justify-end pt-1">
            <button type="button" onClick={onClose} className="rounded-md border border-white/10 bg-[#161B22] px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-white/[0.04] hover:text-white">Cancel</button>
            <button type="submit" disabled={saving} className="flex items-center gap-2 rounded-md border border-blue-400/30 bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:opacity-50">
              {saving && <Spinner size={13} />}
              {saving ? "Creating…" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const INPUT = "w-full rounded-md border border-white/10 bg-[#11161C] px-3 py-2 text-sm text-white placeholder:text-slate-600 transition-colors focus:border-blue-500/70 focus:outline-none focus:ring-2 focus:ring-blue-500/30";

function inputClass(error?: string) {
  return `${INPUT} ${error ? "border-red-700 focus:ring-red-500 focus:border-red-600" : ""}`;
}

function FieldError({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-red-300">
      <AlertCircle size={11} />
      <span>{children}</span>
    </div>
  );
}

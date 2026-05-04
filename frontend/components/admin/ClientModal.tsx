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
      <div className="relative mx-4 w-full max-w-md rounded-lg border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <div>
            <h2 className="text-sm font-semibold text-white">New client organisation</h2>
            <p className="mt-0.5 text-[11px] text-slate-500">Create the tenant used for uploads, reviewers, and reporting.</p>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-300" aria-label="Close client dialog">
            <X size={16} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-800 bg-red-950/60 px-3 py-2.5 text-xs text-red-300">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <section className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Organisation name <span className="text-red-400">*</span></label>
            <input value={name} onChange={e => setName(e.target.value)} required
              placeholder="Acme Lending" className={inputClass(fieldErrors.name)} />
            {fieldErrors.name && <FieldError>{fieldErrors.name}</FieldError>}
          </section>
          <section className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Short code <span className="text-red-400">*</span></label>
            <input value={code} onChange={e => setCode(e.target.value.toUpperCase())} required
              placeholder="ACME" maxLength={10} className={inputClass(fieldErrors.code)} />
            <p className="text-[11px] text-slate-600 mt-1">2-10 chars. Used in file storage paths and batch cleanup.</p>
            {fieldErrors.code && <FieldError>{fieldErrors.code}</FieldError>}
          </section>
          <div className="flex gap-2 justify-end pt-1">
            <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium transition-colors">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium transition-colors flex items-center gap-2">
              {saving && <Spinner size={13} />}
              {saving ? "Creating…" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const INPUT = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-colors";

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

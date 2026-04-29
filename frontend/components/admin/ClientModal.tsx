"use client";
import { useState } from "react";
import { X } from "lucide-react";
import { createClient } from "@/lib/api";
import Spinner from "@/components/shared/Spinner";

interface Props { open: boolean; onClose: () => void; onSaved: () => void; }

export default function ClientModal({ open, onClose, onSaved }: Props) {
  const [name, setName]     = useState("");
  const [code, setCode]     = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState("");

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
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
      <div className="relative bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-sm mx-4 shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h2 className="text-sm font-semibold text-white">New client organisation</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
            <X size={16} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="text-xs text-red-300 bg-red-950/60 border border-red-800 rounded-lg px-3 py-2.5">{error}</div>
          )}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Organisation name <span className="text-red-400">*</span></label>
            <input value={name} onChange={e => setName(e.target.value)} required
              placeholder="Acme Lending" className={INPUT} />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Short code <span className="text-red-400">*</span></label>
            <input value={code} onChange={e => setCode(e.target.value.toUpperCase())} required
              placeholder="ACME" maxLength={10} className={INPUT} />
            <p className="text-[11px] text-slate-600 mt-1">Uppercase, max 10 chars. Used in file storage paths.</p>
          </div>
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

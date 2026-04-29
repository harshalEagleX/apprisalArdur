"use client";
import { useState } from "react";
import { createClient } from "@/lib/api";

interface ClientModalProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export default function ClientModal({ open, onClose, onSaved }: ClientModalProps) {
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
      onSaved();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create client");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-sm mx-4 shadow-2xl">
        <h3 className="text-lg font-semibold text-white mb-4">Add Client Organisation</h3>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-900/40 border border-red-700 text-red-300 text-sm">{error}</div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Organisation Name <span className="text-red-400">*</span></label>
            <input value={name} onChange={e => setName(e.target.value)} required
              placeholder="Acme Lending" className={INPUT} />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Short Code <span className="text-red-400">*</span></label>
            <input value={code} onChange={e => setCode(e.target.value.toUpperCase())} required
              placeholder="ACME" maxLength={10} className={INPUT} />
            <p className="text-slate-500 text-xs mt-1">Uppercase letters only, max 10 chars. Used in file paths.</p>
          </div>
          <div className="flex gap-3 justify-end pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 text-sm font-medium transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium transition-colors">
              {saving ? "Creating…" : "Create Client"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const INPUT = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500";

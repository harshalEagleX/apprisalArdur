"use client";
import { useState, useEffect } from "react";
import { X } from "lucide-react";
import { createUser, updateUser, getClients, type User, type Client } from "@/lib/api";
import Spinner from "@/components/shared/Spinner";

interface Props {
  open: boolean;
  user?: User | null;
  onClose: () => void;
  onSaved: () => void;
}

export default function UserModal({ open, user, onClose, onSaved }: Props) {
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole]         = useState<"ADMIN" | "REVIEWER">("REVIEWER");
  const [clientId, setClientId] = useState<number | "">("");
  const [clients, setClients]   = useState<Client[]>([]);
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState("");
  const isEdit = !!user;

  useEffect(() => {
    if (!open) return;
    setUsername(user?.username ?? "");
    setFullName(user?.fullName ?? "");
    setEmail(user?.email ?? "");
    setPassword("");
    setRole((user?.role === "ADMIN" ? "ADMIN" : "REVIEWER"));
    setClientId(user?.client?.id ?? "");
    setError("");
    getClients().then(setClients).catch(() => null);
  }, [open, user]);

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!isEdit && !password) { setError("Password is required"); return; }
    setSaving(true);
    try {
      if (isEdit && user) {
        await updateUser(user.id, { fullName, email, role, clientId: clientId || undefined } as Parameters<typeof updateUser>[1]);
      } else {
        await createUser({ username, password, fullName, email, role, clientId: clientId || undefined } as Parameters<typeof createUser>[0]);
      }
      onSaved();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md mx-4 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h2 className="text-sm font-semibold text-white">{isEdit ? "Edit user" : "New user"}</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="text-xs text-red-300 bg-red-950/60 border border-red-800 rounded-lg px-3 py-2.5">
              {error}
            </div>
          )}

          {!isEdit && (
            <Field label="Username" required>
              <input value={username} onChange={e => setUsername(e.target.value)} required
                placeholder="jane.smith" className={INPUT} />
            </Field>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field label="Full name">
              <input value={fullName} onChange={e => setFullName(e.target.value)}
                placeholder="Jane Smith" className={INPUT} />
            </Field>
            <Field label="Email">
              <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="jane@firm.com" className={INPUT} />
            </Field>
          </div>

          {!isEdit && (
            <Field label="Password" required>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder="Min. 8 characters" required minLength={8} className={INPUT} />
            </Field>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field label="Role" required>
              <select value={role} onChange={e => setRole(e.target.value as "ADMIN" | "REVIEWER")} className={INPUT}>
                <option value="REVIEWER">Reviewer</option>
                <option value="ADMIN">Admin</option>
              </select>
            </Field>
            <Field label="Client org">
              <select value={clientId} onChange={e => setClientId(e.target.value ? Number(e.target.value) : "")} className={INPUT}>
                <option value="">None</option>
                {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
          </div>

          <div className="flex gap-2 justify-end pt-1">
            <button type="button" onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium transition-colors flex items-center gap-2">
              {saving && <Spinner size={13} />}
              {saving ? "Saving…" : isEdit ? "Save changes" : "Create user"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const INPUT = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-colors";

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-400 mb-1.5">
        {label}{required && <span className="text-red-400 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}

"use client";
import { useState } from "react";
import { createUser, updateUser, getClients, type User, type Client } from "@/lib/api";
import { useEffect } from "react";

interface UserModalProps {
  open: boolean;
  user?: User | null;
  onClose: () => void;
  onSaved: () => void;
}

export default function UserModal({ open, user, onClose, onSaved }: UserModalProps) {
  const [username, setUsername]   = useState(user?.username ?? "");
  const [fullName, setFullName]   = useState(user?.fullName ?? "");
  const [email, setEmail]         = useState(user?.email ?? "");
  const [password, setPassword]   = useState("");
  const [role, setRole]           = useState<"ADMIN" | "REVIEWER">(
    (user?.role === "ADMIN" || user?.role === "REVIEWER") ? user.role : "REVIEWER"
  );
  const [clientId, setClientId]   = useState<number | "">(user?.client?.id ?? "");
  const [clients, setClients]     = useState<Client[]>([]);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState("");

  const isEdit = !!user;

  useEffect(() => {
    if (!open) return;
    setUsername(user?.username ?? "");
    setFullName(user?.fullName ?? "");
    setEmail(user?.email ?? "");
    setPassword("");
    setRole((user?.role === "ADMIN" || user?.role === "REVIEWER") ? user.role : "REVIEWER");
    setClientId(user?.client?.id ?? "");
    setError("");
    getClients().then(setClients).catch(() => null);
  }, [open, user]);

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      if (isEdit && user) {
        await updateUser(user.id, { fullName, email, role, clientId: clientId || undefined } as Parameters<typeof updateUser>[1]);
      } else {
        if (!password) { setError("Password is required"); setSaving(false); return; }
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
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-md mx-4 shadow-2xl">
        <h3 className="text-lg font-semibold text-white mb-4">{isEdit ? "Edit User" : "Add User"}</h3>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-900/40 border border-red-700 text-red-300 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {!isEdit && (
            <Field label="Username" required>
              <input value={username} onChange={e => setUsername(e.target.value)}
                placeholder="e.g. john.doe" required className={INPUT} />
            </Field>
          )}
          <Field label="Full Name">
            <input value={fullName} onChange={e => setFullName(e.target.value)}
              placeholder="John Doe" className={INPUT} />
          </Field>
          <Field label="Email">
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="john@example.com" className={INPUT} />
          </Field>
          {!isEdit && (
            <Field label="Password" required>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder="Minimum 8 characters" required minLength={8} className={INPUT} />
            </Field>
          )}
          <Field label="Role" required>
            <select value={role} onChange={e => setRole(e.target.value as "ADMIN" | "REVIEWER")}
              className={INPUT}>
              <option value="REVIEWER">Reviewer</option>
              <option value="ADMIN">Admin</option>
            </select>
          </Field>
          <Field label="Client Organisation (optional)">
            <select value={clientId} onChange={e => setClientId(e.target.value ? Number(e.target.value) : "")}
              className={INPUT}>
              <option value="">— None —</option>
              {clients.map(c => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}
            </select>
          </Field>

          <div className="flex gap-3 justify-end pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 text-sm font-medium transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium transition-colors">
              {saving ? "Saving…" : isEdit ? "Save Changes" : "Create User"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const INPUT = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500";

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-300 mb-1">
        {label}{required && <span className="text-red-400 ml-1">*</span>}
      </label>
      {children}
    </div>
  );
}

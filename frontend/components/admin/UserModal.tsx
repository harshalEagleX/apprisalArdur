"use client";
import { useState, useEffect } from "react";
import { AlertCircle, X } from "lucide-react";
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
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const isEdit = !!user;

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => {
      setUsername(user?.username ?? "");
      setFullName(user?.fullName ?? "");
      setEmail(user?.email ?? "");
      setPassword("");
      setRole((user?.role === "ADMIN" ? "ADMIN" : "REVIEWER"));
      setClientId(user?.client?.id ?? "");
      setError("");
      setFieldErrors({});
      getClients().then(setClients).catch(() => null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [open, user]);

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const nextErrors: Record<string, string> = {};
    if (!isEdit && !username.trim()) nextErrors.username = "Username is required.";
    if (!isEdit && password.length < 8) nextErrors.password = "Password must be at least 8 characters.";
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) nextErrors.email = "Enter a valid email address.";
    if (role === "REVIEWER" && !clientId) nextErrors.clientId = "Assign reviewers to a client organisation.";
    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      setError("Fix the highlighted fields before saving.");
      return;
    }
    setSaving(true);
    try {
      const scopedClientId = role === "REVIEWER" ? clientId || undefined : undefined;
      if (isEdit && user) {
        await updateUser(user.id, { fullName, email, role, clientId: scopedClientId } as Parameters<typeof updateUser>[1]);
      } else {
        await createUser({ username, password, fullName, email, role, clientId: scopedClientId } as Parameters<typeof createUser>[0]);
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
      <div className="relative mx-4 w-full max-w-xl rounded-lg border border-slate-700 bg-slate-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <div>
            <h2 className="text-sm font-semibold text-white">{isEdit ? "Edit user" : "New user"}</h2>
            <p className="mt-0.5 text-[11px] text-slate-500">Keep access scoped to the user’s actual role.</p>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-300" aria-label="Close user dialog">
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
            <div className="mb-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Identity</h3>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {!isEdit && (
                <Field label="Username" required error={fieldErrors.username}>
                  <input value={username} onChange={e => setUsername(e.target.value)} required
                    placeholder="jane.smith" className={inputClass(fieldErrors.username)} />
                </Field>
              )}
            <Field label="Full name">
              <input value={fullName} onChange={e => setFullName(e.target.value)}
                placeholder="Jane Smith" className={INPUT} />
            </Field>
            <Field label="Email" error={fieldErrors.email}>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="jane@firm.com" className={inputClass(fieldErrors.email)} />
            </Field>
            </div>
          </section>

          {!isEdit && (
            <section className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <Field label="Password" required error={fieldErrors.password}>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder="Min. 8 characters" required minLength={8} className={inputClass(fieldErrors.password)} />
            </Field>
            </section>
          )}

          <section className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Role" required>
              <select value={role} onChange={e => setRole(e.target.value as "ADMIN" | "REVIEWER")} className={INPUT}>
                <option value="REVIEWER">Reviewer</option>
                <option value="ADMIN">Admin</option>
              </select>
            </Field>
            {role === "REVIEWER" && (
            <Field label="Client org" required error={fieldErrors.clientId}>
              <select value={clientId} onChange={e => setClientId(e.target.value ? Number(e.target.value) : "")} className={inputClass(fieldErrors.clientId)}>
                <option value="">None</option>
                {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            )}
          </div>
          {role === "ADMIN" && (
            <p className="mt-2 text-[11px] text-slate-600">Admins are platform-scoped, so client organisation is not required.</p>
          )}
          </section>

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

function inputClass(error?: string) {
  return `${INPUT} ${error ? "border-red-700 focus:ring-red-500 focus:border-red-600" : ""}`;
}

function Field({ label, required, error, children }: { label: string; required?: boolean; error?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-400 mb-1.5">
        {label}{required && <span className="text-red-400 ml-0.5">*</span>}
      </label>
      {children}
      {error && (
        <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-red-300">
          <AlertCircle size={11} />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

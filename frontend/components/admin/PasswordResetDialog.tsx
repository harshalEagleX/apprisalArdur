"use client";
import { useEffect, useState } from "react";
import { Eye, EyeOff, KeyRound } from "lucide-react";
import Modal from "@/components/shared/Modal";
import Spinner from "@/components/shared/Spinner";
import { getPasswordPolicy, type User } from "@/lib/api";

/**
 * Admin password reset.
 *
 * Replaces a `window.prompt()`, which echoed the new password in clear text in a
 * browser chrome box, could not confirm it, and hard-coded a minimum length that
 * had already drifted from the backend policy. The minimum is now read from
 * /api/config/password-policy so this dialog can never disagree with the server.
 */
export default function PasswordResetDialog({
  user,
  submitting,
  onSubmit,
  onCancel,
}: {
  user: User | null;
  submitting: boolean;
  onSubmit: (password: string) => void;
  onCancel: () => void;
}) {
  if (!user) return null;
  // Keyed by user id: opening the dialog for a different account remounts it, so
  // the fields start empty without an effect that resets state after render.
  return (
    <PasswordResetForm
      key={user.id}
      user={user}
      submitting={submitting}
      onSubmit={onSubmit}
      onCancel={onCancel}
    />
  );
}

function PasswordResetForm({
  user,
  submitting,
  onSubmit,
  onCancel,
}: {
  user: User;
  submitting: boolean;
  onSubmit: (password: string) => void;
  onCancel: () => void;
}) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [reveal, setReveal] = useState(false);
  const [minLength, setMinLength] = useState(8);

  // Read the server's real policy so this dialog can never state a rule the
  // backend disagrees with. The conservative default stands if the call fails.
  useEffect(() => {
    let active = true;
    getPasswordPolicy()
      .then(p => {
        if (active && typeof p.minLength === "number" && p.minLength > 0) setMinLength(p.minLength);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  const tooShort = password.length > 0 && password.length < minLength;
  const mismatch = confirm.length > 0 && confirm !== password;
  const canSubmit = password.length >= minLength && confirm === password && !submitting;

  const fieldClass =
    "h-9 w-full rounded-md border bg-sunken px-3 pr-9 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:ring-2";

  return (
    <Modal onClose={onCancel} labelledBy="password-reset-title" describedBy="password-reset-desc" autoFocus={false}>
      <div className="mb-4 flex gap-3">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border border-slate-500/30 bg-slate-950/50">
          <KeyRound size={16} className="text-slate-400" />
        </div>
        <div className="min-w-0">
          <h3 id="password-reset-title" className="text-sm font-semibold text-white">Reset password</h3>
          <p id="password-reset-desc" className="mt-0.5 text-sm leading-relaxed text-slate-400">
            Set a new password for <span className="font-medium text-slate-200">{user.username}</span>. They can sign in
            with it immediately — share it over a trusted channel.
          </p>
        </div>
      </div>

      <form
        onSubmit={e => { e.preventDefault(); if (canSubmit) onSubmit(password); }}
        className="space-y-3"
      >
        <div>
          <label htmlFor="new-password" className="mb-1 block text-xs font-medium text-slate-400">New password</label>
          <div className="relative">
            <input
              id="new-password"
              type={reveal ? "text" : "password"}
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoFocus
              autoComplete="new-password"
              aria-invalid={tooShort}
              aria-describedby="password-rule"
              className={`${fieldClass} ${tooShort ? "border-red-500/40 focus:ring-red-500/30" : "border-white/10 focus:ring-slate-500/30"}`}
            />
            <button
              type="button"
              onClick={() => setReveal(v => !v)}
              aria-label={reveal ? "Hide password" : "Show password"}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 transition-colors hover:text-slate-300"
            >
              {reveal ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
          <p id="password-rule" className={`mt-1 text-[11px] ${tooShort ? "text-red-300" : "text-slate-600"}`}>
            {tooShort
              ? `Needs at least ${minLength} characters — ${minLength - password.length} to go.`
              : `At least ${minLength} characters.`}
          </p>
        </div>

        <div>
          <label htmlFor="confirm-password" className="mb-1 block text-xs font-medium text-slate-400">Confirm password</label>
          <input
            id="confirm-password"
            type={reveal ? "text" : "password"}
            value={confirm}
            onChange={e => setConfirm(e.target.value)}
            autoComplete="new-password"
            aria-invalid={mismatch}
            className={`${fieldClass} ${mismatch ? "border-red-500/40 focus:ring-red-500/30" : "border-white/10 focus:ring-slate-500/30"}`}
          />
          {mismatch && <p className="mt-1 text-[11px] text-red-300">The two passwords do not match.</p>}
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-white/10 px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-white/[0.04] focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400/50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-500 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/40"
          >
            {submitting && <Spinner size={13} />}
            {submitting ? "Setting…" : "Set password"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

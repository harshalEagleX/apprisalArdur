"use client";
import React, { useEffect, useRef } from "react";
import { AlertTriangle, AlertCircle } from "lucide-react";

function SignOffStat({
  label,
  value,
  danger,
}: {
  label: string;
  value: number;
  danger?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border px-2.5 py-2 ${danger ? "border-red-500/25 bg-red-950/30 text-red-200" : "border-white/10 bg-[#0B0F14]/60 text-slate-200"}`}
    >
      <div className="text-base font-semibold tabular-nums">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}

export interface SignOffDialogProps {
  open: boolean;
  qcResultId: number;
  totalReviewed: number;
  passed: number;
  failed: number;
  notes: string;
  submitting: boolean;
  submitError?: string;
  onNotesChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export function SignOffDialog({
  open,
  qcResultId,
  totalReviewed,
  passed,
  failed,
  notes,
  submitting,
  submitError,
  onNotesChange,
  onCancel,
  onConfirm,
}: SignOffDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const timer = window.setTimeout(() => dialogRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(timer);
      previousFocusRef.current?.focus();
    };
  }, [open]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape" && !submitting) {
      e.preventDefault();
      onCancel();
      return;
    }
    if (e.key !== "Tab") return;
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable || focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={submitting ? undefined : onCancel}
      />
      <div
        ref={dialogRef}
        className="relative w-full max-w-sm rounded-lg border border-white/10 bg-[#11161C] p-5 shadow-[0_22px_60px_rgba(0,0,0,0.46)] focus:outline-none"
        role="dialog"
        aria-modal="true"
        aria-labelledby="signoff-dialog-title"
        aria-describedby="signoff-dialog-description"
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-amber-500/25 bg-amber-950/50">
            <AlertTriangle size={16} className="text-amber-300" />
          </div>
          <div className="min-w-0">
            <h3 id="signoff-dialog-title" className="text-sm font-semibold text-white">
              Submit review
            </h3>
            <p id="signoff-dialog-description" className="mt-1 text-sm leading-relaxed text-slate-400">
              This will sign off QC Result #{qcResultId}. The action cannot be undone.
            </p>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          <SignOffStat label="Reviewed" value={totalReviewed} />
          <SignOffStat label="Passed"   value={passed} />
          <SignOffStat label="Failed"   value={failed} danger={failed > 0} />
        </div>

        {failed > 0 && !submitError && (
          <div className="mt-3 rounded-lg border border-red-500/25 bg-red-950/20 px-3 py-2 text-xs text-red-200 leading-relaxed">
            {failed} rule{failed === 1 ? "" : "s"} confirmed as fail. Rejection language will be generated after submission.
          </div>
        )}

        {submitError && (
          <div className="mt-3 rounded-lg border border-red-500/40 bg-red-950/35 px-3 py-2.5 text-xs text-red-200 leading-relaxed flex items-start gap-2">
            <AlertCircle size={13} className="flex-shrink-0 mt-0.5 text-red-400" />
            <span>{submitError}</span>
          </div>
        )}

        <label className="mt-4 block text-xs font-medium text-slate-400">Sign-off notes (optional)</label>
        <textarea
          value={notes}
          onChange={e => onNotesChange(e.target.value)}
          autoFocus
          rows={3}
          className="mt-1.5 w-full resize-none rounded-md border border-white/10 bg-[#0B0F14]/70 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 transition-colors focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30"
          placeholder="Summary for the completed review..."
        />

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={submitting}
            className="h-9 rounded-md border border-white/10 bg-[#161B22] px-4 text-sm font-medium text-slate-300 transition-colors hover:bg-white/[0.04] hover:text-white disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={submitting}
            className="h-9 rounded-md border border-slate-400/30 bg-slate-600 px-4 text-sm font-semibold text-white transition-colors hover:bg-slate-500 disabled:opacity-40"
          >
            {submitting ? "Submitting…" : "Submit review"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SignOffDialog;

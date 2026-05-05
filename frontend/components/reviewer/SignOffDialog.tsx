"use client";
import React, { useEffect, useRef } from "react";
import { AlertTriangle } from "lucide-react";

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
      className={`rounded-lg border px-2.5 py-2 ${danger ? "border-red-900/50 bg-red-950/30 text-red-200" : "border-slate-800 bg-slate-950/50 text-slate-200"}`}
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
  code: string;
  notes: string;
  submitting: boolean;
  onCodeChange: (value: string) => void;
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
  code,
  notes,
  submitting,
  onCodeChange,
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

  const expected = String(qcResultId).slice(-4);
  const canConfirm = code.trim() === expected && !submitting;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={submitting ? undefined : onCancel}
      />
      <div
        ref={dialogRef}
        className="relative w-full max-w-sm rounded-lg border border-slate-700 bg-slate-900 p-5 shadow-2xl focus:outline-none"
        role="dialog"
        aria-modal="true"
        aria-labelledby="signoff-dialog-title"
        aria-describedby="signoff-dialog-description"
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-amber-800 bg-amber-950/60">
            <AlertTriangle size={16} className="text-amber-300" />
          </div>
          <div className="min-w-0">
            <h3
              id="signoff-dialog-title"
              className="text-sm font-semibold text-white"
            >
              Submit review
            </h3>
            <p
              id="signoff-dialog-description"
              className="mt-1 text-sm leading-relaxed text-slate-400"
            >
              This will sign off QC Result #{qcResultId}. The action cannot be undone.
            </p>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          <SignOffStat label="Reviewed" value={totalReviewed} />
          <SignOffStat label="Passed" value={passed} />
          <SignOffStat label="Failed" value={failed} danger={failed > 0} />
        </div>

        <label className="mt-4 block text-xs font-medium text-slate-400">
          Type last 4 digits:{" "}
          <span className="font-mono text-slate-200">{expected}</span>
        </label>
        <input
          value={code}
          onChange={e => onCodeChange(e.target.value)}
          autoFocus
          inputMode="numeric"
          maxLength={4}
          className="mt-1.5 h-10 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 font-mono text-sm tracking-[0.25em] text-white placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
          placeholder="0000"
        />

        <label className="mt-4 block text-xs font-medium text-slate-400">Sign-off notes</label>
        <textarea
          value={notes}
          onChange={e => onNotesChange(e.target.value)}
          rows={3}
          className="mt-1.5 w-full resize-none rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
          placeholder="Optional summary for the completed review..."
        />

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={submitting}
            className="h-9 rounded-lg bg-slate-800 px-4 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-700 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!canConfirm}
            className="h-9 rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:opacity-40"
          >
            {submitting ? "Submitting..." : "Submit review"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SignOffDialog;

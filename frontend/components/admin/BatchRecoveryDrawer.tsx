"use client";
import React, { useEffect, useRef } from "react";
import { AlertTriangle, XCircle, Play, Trash2, FileStack, Upload } from "lucide-react";
import type { Batch } from "@/lib/api";
import { toast } from "@/lib/toast";

function RecoveryMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone: "slate" | "amber" | "blue" | "green" | "red";
}) {
  const tones = {
    slate: "border-white/10 bg-[#0B0F14]/70 text-slate-300",
    amber: "border-amber-900/50 bg-amber-950/30 text-amber-200",
    blue: "border-blue-900/50 bg-blue-950/30 text-blue-200",
    green: "border-green-900/50 bg-green-950/30 text-green-200",
    red: "border-red-900/50 bg-red-950/30 text-red-200",
  };
  return (
    <div className={`rounded-md border px-3 py-2 ${tones[tone]}`}>
      <div className="text-sm font-semibold tabular-nums">{value}</div>
      <div className="mt-0.5 text-[10px] uppercase tracking-wide opacity-70">{label}</div>
    </div>
  );
}

function recoveryAdvice(batch: Batch): {
  stage: string;
  fix: string;
  reupload: string;
} {
  const message = (batch.errorMessage ?? "").toLowerCase();
  if (
    batch.status === "VALIDATION_FAILED" ||
    message.includes("zip") ||
    message.includes("folder") ||
    message.includes("validation")
  ) {
    return {
      stage: "Upload validation",
      fix: "Check the ZIP structure and file naming, then upload a corrected archive. QC cannot run until validation passes.",
      reupload:
        "Use Upload replacement after deleting this failed batch if the archive contents need to change.",
    };
  }
  if (message.includes("timeout") || message.includes("timed out")) {
    return {
      stage: "QC processing",
      fix: "Retry QC once. If it fails again, reconcile stuck batches and check whether the OCR/QC service is healthy.",
      reupload:
        "Re-upload only if the same document repeatedly times out or appears corrupted.",
    };
  }
  if (
    message.includes("ocr") ||
    message.includes("python") ||
    message.includes("model")
  ) {
    return {
      stage: "OCR or model service",
      fix: "Confirm the QC model service is running, then use Reconcile from the batch page before retrying QC.",
      reupload: "Re-upload is usually unnecessary unless the source PDF cannot be opened.",
    };
  }
  return {
    stage: "QC processing",
    fix: "Retry QC. If the same error returns, run Reconcile and preserve the full error text for support.",
    reupload: "Delete and re-upload only when the archive or PDFs are known to be wrong.",
  };
}

async function copyBatchError(batch: Batch): Promise<void> {
  const text = [
    `Batch: ${batch.parentBatchId}`,
    `Status: ${batch.status}`,
    `Client: ${batch.client?.name ?? "No client"}`,
    `Files: ${batch.fileCount ?? batch.files?.length ?? 0}`,
    "",
    batch.errorMessage || "No error message provided.",
  ].join("\n");
  try {
    await navigator.clipboard.writeText(text);
    toast.success("Batch error copied");
  } catch {
    toast.error("Could not copy error");
  }
}

export interface BatchRecoveryDrawerProps {
  batch: Batch | null;
  busy: boolean;
  onClose: () => void;
  onRetry: (batch: Batch) => void;
  onDelete: (batch: Batch) => void;
  onReupload: () => void;
}

export function BatchRecoveryDrawer({
  batch,
  busy,
  onClose,
  onRetry,
  onDelete,
  onReupload,
}: BatchRecoveryDrawerProps) {
  const drawerRef = useRef<HTMLElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!batch) return;
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const timer = window.setTimeout(() => drawerRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(timer);
      previousFocusRef.current?.focus();
    };
  }, [batch]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key !== "Tab") return;
    const focusable = drawerRef.current?.querySelectorAll<HTMLElement>(
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

  if (!batch) return null;

  const advice = recoveryAdvice(batch);
  const fileCount = batch.fileCount ?? batch.files?.length ?? 0;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <aside
        ref={drawerRef}
        className="relative flex h-full w-full max-w-lg flex-col border-l border-white/10 bg-[#0B0F14] shadow-[0_0_60px_rgba(0,0,0,0.5)]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="batch-recovery-title"
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-start gap-3 border-b border-white/10 p-5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-red-500/25 bg-red-950/40 text-red-300">
            <AlertTriangle size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <h2
              id="batch-recovery-title"
              className="text-sm font-semibold text-white"
            >
              Batch recovery
            </h2>
            <div
              className="mt-1 truncate font-mono text-xs text-slate-400"
              title={batch.parentBatchId}
            >
              {batch.parentBatchId}
            </div>
          </div>
          <button
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-white/[0.04] hover:text-slate-300"
            aria-label="Close recovery drawer"
          >
            <XCircle size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          <div className="grid grid-cols-2 gap-2">
            <RecoveryMetric label="Status" value={batch.status.replace(/_/g, " ")} tone="red" />
            <RecoveryMetric label="Files" value={fileCount} tone="slate" />
            <RecoveryMetric label="Client" value={batch.client?.name ?? "No client"} tone="slate" />
            <RecoveryMetric label="Failed stage" value={advice.stage} tone="amber" />
          </div>

          <section className="mt-5 rounded-lg border border-red-500/25 bg-red-950/20 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-red-200">
              Full error
            </h3>
            <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-red-100/85">
              {batch.errorMessage ||
                "The backend did not provide a detailed error message for this batch."}
            </p>
          </section>

          <section className="mt-4 rounded-lg border border-white/10 bg-[#11161C]/80 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Suggested recovery
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-300">{advice.fix}</p>
            <div className="mt-3 text-xs leading-relaxed text-slate-500">{advice.reupload}</div>
          </section>
        </div>

        <div className="border-t border-white/10 p-4">
          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={() => void copyBatchError(batch)}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-white/10 bg-[#11161C] px-3 text-sm text-slate-300 transition-colors hover:bg-white/[0.04] hover:text-white"
            >
              <FileStack size={14} /> Copy error
            </button>
            <button
              onClick={() => onRetry(batch)}
              disabled={busy || batch.status === "VALIDATION_FAILED"}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-blue-400/30 bg-blue-600 px-3 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:opacity-40"
            >
              <Play size={14} /> Retry QC
            </button>
            <button
              onClick={onReupload}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-white/10 bg-[#11161C] px-3 text-sm text-slate-300 transition-colors hover:bg-white/[0.04] hover:text-white"
            >
              <Upload size={14} /> Upload replacement
            </button>
            <button
              onClick={() => onDelete(batch)}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-red-500/25 bg-red-950/30 px-3 text-sm text-red-200 transition-colors hover:bg-red-950/60"
            >
              <Trash2 size={14} /> Delete batch
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}

export default BatchRecoveryDrawer;

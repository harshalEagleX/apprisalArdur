"use client";
import React, { memo } from "react";
import { Play, RefreshCw, Square, Trash2, AlertTriangle, AlertCircle, UserPlus, History } from "lucide-react";
import type { Batch, User } from "@/lib/api";
import { displayName } from "@/lib/displayName";
import StatusBadge from "@/components/shared/StatusBadge";
import { ReviewerAssignControl } from "./ReviewerAssignControl";
import type { BatchProgress } from "@/hooks/useBatchPolling";

export interface BatchRowProps {
  batch: Batch;
  isLoading: boolean;
  progress: BatchProgress | undefined;
  reviewers: User[];
  reviewerWorkload: Record<string, number>;
  onProcessQC: (batch: Batch) => void;
  onStopQC: (batch: Batch) => void;
  onAssign: (batchId: number, reviewerId: number) => void;
  onDelete: (batch: Batch) => void;
  onOpenRecovery: (batch: Batch) => void;
  onOpenHistory: (batch: Batch) => void;
  // Bulk-selection
  selected?: boolean;
  onSelect?: (id: number, checked: boolean) => void;
}

export const BatchRow = memo(function BatchRow({
  batch,
  isLoading,
  progress,
  reviewers,
  reviewerWorkload,
  onProcessQC,
  onStopQC,
  onAssign,
  onDelete,
  onOpenRecovery,
  onOpenHistory,
  selected = false,
  onSelect,
}: BatchRowProps) {
  const b = batch;
  const pct = progress ? (progress.smoothedPercent ?? progress.percent) : 0;
  const subLabel = progress?.subStage ? progress.subStage.replace(/_/g, " ") : null;

  // "Stuck" heuristic: QC is flagged in-flight but there are NO live progress
  // frames AND the batch row hasn't been touched for a while. A healthy long
  // run keeps streaming progress, so requiring both conditions avoids false
  // positives on slow-but-alive jobs. When true, the worker likely died or the
  // job was lost — the admin can Stop and start again.
  const STUCK_GRACE_MIN = 4;
  const minsSinceUpdate = b.updatedAt ? (Date.now() - Date.parse(b.updatedAt)) / 60000 : 0;
  const maybeStuck =
    b.status === "QC_PROCESSING" && !progress && minsSinceUpdate >= STUCK_GRACE_MIN;

  const spinnerSvg = (
    <svg
      className="animate-spin h-3 w-3"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );

  return (
    <tr
      className={`transition-colors ${selected ? "bg-indigo-950/20" : b.status === "QC_PROCESSING" ? "bg-slate-950/10" : "hover:bg-white/[0.03]"}`}
    >
      {/* Bulk-select checkbox */}
      <td className="w-10 px-3 py-3" onClick={e => e.stopPropagation()}>
        {onSelect && (
          <input
            type="checkbox"
            checked={selected}
            onChange={e => onSelect(b.id, e.target.checked)}
            className="h-4 w-4 rounded border-white/20 bg-[#11161C] accent-indigo-500 cursor-pointer"
            aria-label={`Select batch ${b.parentBatchId}`}
          />
        )}
      </td>

      {/* Batch ID */}
      <td className="px-4 py-3">
        <div
          className="font-mono text-xs text-slate-200 max-w-[190px] truncate"
          title={b.parentBatchId}
        >
          {b.parentBatchId}
        </div>
        {b.status === "ERROR" && (
          <div className="mt-1 inline-flex items-center gap-1 text-[10px] text-red-300">
            <AlertTriangle size={10} /> Retry available
          </div>
        )}
      </td>

      {/* Client */}
      <td className="px-4 py-3 text-xs text-slate-400">
        {b.client?.name ?? <span className="text-slate-600">—</span>}
      </td>

      {/* Status + inline QC progress */}
      <td className="px-4 py-3">
        <StatusBadge status={b.status} />
        {b.intakeWarnings && (
          <div
            className="mt-1.5 flex max-w-[190px] items-start gap-1 rounded-md border border-amber-500/25 bg-amber-950/25 px-1.5 py-1"
            title={b.intakeWarnings}
          >
            <AlertTriangle size={10} className="mt-0.5 flex-shrink-0 text-amber-400" />
            <span className="text-[10px] leading-tight text-amber-300 line-clamp-2">
              Ambiguous documents — confirm before QC
            </span>
          </div>
        )}
        {b.status === "QC_PROCESSING" && progress && (
          <div className="mt-1.5">
            <div className="flex justify-between text-[10px] text-slate-500 mb-0.5">
              <span className="max-w-[150px] truncate" title={progress.message}>
                {progress.message}
              </span>
              <span className="font-mono">{pct}%</span>
            </div>
            <div className="w-32 h-1 bg-[#0B0F14] rounded-full overflow-hidden">
              <div
                className="h-full bg-slate-500 rounded-full transition-all duration-500"
                style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
              />
            </div>
            <div className="mt-0.5 text-[10px] text-slate-600">
              {progress.current}/{progress.total} appraisal set{progress.total === 1 ? "" : "s"} ·{" "}
              {b.fileCount ?? b.files?.length ?? 0} files · {progress.stage.replace(/_/g, " ")}
            </div>
            {subLabel && (
              <div
                className="mt-0.5 text-[10px] text-slate-300 max-w-[170px] truncate"
                title={progress.subMessage ?? subLabel}
              >
                {subLabel}
                {progress.subMessage ? ` — ${progress.subMessage}` : ""}
              </div>
            )}
            {progress.modelName && (
              <div className="mt-0.5 text-[10px] text-slate-400 max-w-[150px] truncate">
                {progress.modelProvider ?? "model"} · {progress.modelName}
              </div>
            )}
          </div>
        )}
        {maybeStuck && (
          <div
            className="mt-1.5 flex max-w-[190px] items-start gap-1 rounded-md border border-amber-500/30 bg-amber-950/30 px-1.5 py-1"
            title={`No progress for ${Math.floor(minsSinceUpdate)} min. The QC worker may have stopped or the job was lost. Stop this run and start it again, or check the worker.`}
          >
            <AlertTriangle size={10} className="mt-0.5 flex-shrink-0 text-amber-400" />
            <span className="text-[10px] leading-tight text-amber-300">
              No progress for {Math.floor(minsSinceUpdate)} min — may be stuck
            </span>
          </div>
        )}
        {b.errorMessage &&
          (b.status === "ERROR" || b.status === "VALIDATION_FAILED") && (
            <button
              type="button"
              onClick={() => onOpenRecovery(b)}
              className="mt-1.5 flex max-w-[170px] items-start gap-1 rounded-md text-left transition-colors hover:bg-red-950/30"
              title={b.errorMessage}
            >
              <AlertCircle size={10} className="text-red-400 flex-shrink-0 mt-0.5" />
              <span className="text-[10px] text-red-400 leading-tight line-clamp-2 max-w-[120px]">
                {b.errorMessage}
              </span>
            </button>
          )}
      </td>

      {/* Files */}
      <td className="px-4 py-3 text-xs text-slate-400 tabular-nums">
        {b.fileCount ?? b.files?.length ?? 0}
      </td>

      {/* Reviewer */}
      <td className="px-4 py-3 text-xs">
        {b.assignedReviewer ? (
          <span className="text-slate-300" title={b.assignedReviewer.username}>
            {b.assignedReviewer.fullName ?? displayName(b.assignedReviewer.username)}
          </span>
        ) : (
          <span className="text-slate-600">Unassigned</span>
        )}
      </td>

      {/* Date */}
      <td className="px-4 py-3 text-xs text-slate-500">
        {new Date(b.createdAt).toLocaleDateString("en-GB", {
          day: "numeric",
          month: "short",
          year: "numeric",
        })}
      </td>

      {/* Actions */}
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-1.5">
          {/* Run QC */}
          {(b.status === "UPLOADED" ||
            b.status === "VALIDATING" ||
            b.status === "ERROR") && (
            <button
              onClick={() => onProcessQC(b)}
              disabled={isLoading}
              className="inline-flex h-8 min-w-[88px] items-center justify-center gap-1.5 rounded-md border border-slate-500/25 bg-slate-950/45 px-2.5 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-900/50 disabled:opacity-40"
            >
              {isLoading ? spinnerSvg : <Play size={12} />}
              {b.status === "ERROR" ? "Retry" : "Run QC"}
            </button>
          )}

          {/* Processing spinner (no progress yet) — turns amber if it looks stuck */}
          {b.status === "QC_PROCESSING" && !progress && (
            <span
              className={`text-[11px] flex items-center gap-1 ${maybeStuck ? "text-amber-400" : "text-slate-400"}`}
              title={maybeStuck ? "No progress for a while — use Stop, then Run QC again" : undefined}
            >
              {maybeStuck ? <AlertTriangle size={12} /> : spinnerSvg}
              {maybeStuck ? "Stuck?" : "Processing"}
            </span>
          )}

          {/* Re-run QC — available after a successful QC or for review-pending batches */}
          {(b.status === "COMPLETED" || b.status === "REVIEW_PENDING" || b.status === "IN_REVIEW") && (
            <button
              onClick={() => onProcessQC(b)}
              disabled={isLoading}
              className="inline-flex h-8 min-w-[88px] items-center justify-center gap-1.5 rounded-md border border-indigo-500/25 bg-indigo-950/30 px-2.5 text-xs font-medium text-indigo-300 transition-colors hover:bg-indigo-950/60 disabled:opacity-40"
              title="Re-run QC with current rules and model — previous results are preserved until the new run completes"
            >
              {isLoading ? spinnerSvg : <RefreshCw size={12} />}
              Re-run QC
            </button>
          )}

          {/* Stop QC */}
          {b.status === "QC_PROCESSING" && (
            <button
              onClick={() => onStopQC(b)}
              disabled={isLoading}
              className="inline-flex h-8 min-w-[70px] items-center justify-center gap-1 rounded-md border border-red-500/25 bg-red-950/30 px-2.5 text-xs font-medium text-red-200 transition-colors hover:bg-red-950/60 disabled:opacity-40"
              title="Stop QC processing"
            >
              <Square size={11} />
              Stop
            </button>
          )}

          {/* Assign reviewer */}
          {b.status === "QC_PROCESSING" && (
            <span className="flex h-7 items-center rounded-md border border-white/10 px-2 text-[11px] text-slate-500">
              Assign after QC
            </span>
          )}
          {b.status === "REVIEW_PENDING" &&
            (reviewers.length > 0 ? (
              <ReviewerAssignControl
                batch={b}
                reviewers={reviewers}
                workload={reviewerWorkload}
                disabled={isLoading}
                onAssign={reviewerId => onAssign(b.id, reviewerId)}
              />
            ) : (
              <span className="h-7 px-2 rounded-md border border-amber-900/60 text-[11px] text-amber-300 flex items-center">
                <UserPlus size={11} className="mr-1" />
                No reviewers
              </span>
            ))}

          {/* QC history + version diff — only once QC has produced results */}
          {(b.status === "COMPLETED" || b.status === "REVIEW_PENDING" || b.status === "IN_REVIEW") && (
            <button
              onClick={() => onOpenHistory(b)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-indigo-950/40 hover:text-indigo-300"
              title="QC history & version diff"
              aria-label="QC history and version diff"
            >
              <History size={14} />
            </button>
          )}

          {/* Delete */}
          <button
            onClick={() => onDelete(b)}
            disabled={b.status === "QC_PROCESSING"}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-red-950/40 hover:text-red-300 disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-slate-600"
            title={
              b.status === "QC_PROCESSING"
                ? "Stop QC before deleting this batch"
                : "Delete batch"
            }
            aria-label={
              b.status === "QC_PROCESSING"
                ? "Stop QC before deleting this batch"
                : "Delete batch"
            }
          >
            <Trash2 size={14} />
          </button>
        </div>
      </td>
    </tr>
  );
});

export default BatchRow;

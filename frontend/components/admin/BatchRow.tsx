"use client";
import React, { memo } from "react";
import { Play, Square, Trash2, AlertTriangle, AlertCircle, UserPlus } from "lucide-react";
import type { Batch, User } from "@/lib/api";
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
}: BatchRowProps) {
  const b = batch;
  const pct = progress ? (progress.smoothedPercent ?? progress.percent) : 0;
  const subLabel = progress?.subStage ? progress.subStage.replace(/_/g, " ") : null;

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
      className={`transition-colors ${b.status === "QC_PROCESSING" ? "bg-indigo-950/10" : "hover:bg-slate-800/30"}`}
    >
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
        {b.status === "QC_PROCESSING" && progress && (
          <div className="mt-1.5">
            <div className="flex justify-between text-[10px] text-slate-500 mb-0.5">
              <span className="max-w-[150px] truncate" title={progress.message}>
                {progress.message}
              </span>
              <span className="font-mono">{pct}%</span>
            </div>
            <div className="w-32 h-1 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
              />
            </div>
            <div className="mt-0.5 text-[10px] text-slate-600">
              {progress.current}/{progress.total} appraisal set{progress.total === 1 ? "" : "s"} ·{" "}
              {b.fileCount ?? b.files?.length ?? 0} files · {progress.stage.replace(/_/g, " ")}
            </div>
            {subLabel && (
              <div
                className="mt-0.5 text-[10px] text-indigo-300 max-w-[170px] truncate"
                title={progress.subMessage ?? subLabel}
              >
                {subLabel}
                {progress.subMessage ? ` — ${progress.subMessage}` : ""}
              </div>
            )}
            {progress.modelName && (
              <div className="mt-0.5 text-[10px] text-blue-400 max-w-[150px] truncate">
                {progress.modelProvider ?? "model"} · {progress.modelName}
              </div>
            )}
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
          <span className="text-slate-300">
            {b.assignedReviewer.fullName ?? b.assignedReviewer.username}
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
              className="h-8 min-w-[88px] px-2.5 rounded-md bg-indigo-900/50 hover:bg-indigo-800/60 border border-indigo-800/50 text-indigo-200 text-xs font-medium transition-colors disabled:opacity-40 inline-flex items-center justify-center gap-1.5"
            >
              {isLoading ? spinnerSvg : <Play size={12} />}
              {b.status === "ERROR" ? "Retry" : "Run QC"}
            </button>
          )}

          {/* Processing spinner (no progress yet) */}
          {b.status === "QC_PROCESSING" && !progress && (
            <span className="text-[11px] text-indigo-400 flex items-center gap-1">
              {spinnerSvg}
              Processing
            </span>
          )}

          {/* Stop QC */}
          {b.status === "QC_PROCESSING" && (
            <button
              onClick={() => onStopQC(b)}
              disabled={isLoading}
              className="h-8 min-w-[70px] px-2.5 rounded-md border border-red-900/60 bg-red-950/30 hover:bg-red-950/60 text-red-300 text-xs font-medium transition-colors disabled:opacity-40 inline-flex items-center justify-center gap-1"
              title="Stop QC processing"
            >
              <Square size={11} />
              Stop
            </button>
          )}

          {/* Assign reviewer */}
          {b.status === "QC_PROCESSING" && (
            <span className="h-7 px-2 rounded-md border border-slate-800 text-[11px] text-slate-500 flex items-center">
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

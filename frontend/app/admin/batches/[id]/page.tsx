"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, ChevronRight, Package, FileText, CheckCircle2,
  AlertCircle, Clock, UserCheck, AlertTriangle, RefreshCw,
  Play, History, ChevronDown, ChevronUp, XCircle, Building2,
  Link2, RotateCcw,
} from "lucide-react";
import {
  getBatchById, getQCResults, processOrderQC, getFileHistory,
  getQCHistory, assignFileToAppraisal, reclassifyBatchFile, AddressMismatchError,
  type Batch, type QCResult, type PropertySet, type BatchFile,
  type FileHistoryResponse, type QCHistoryRun,
} from "@/lib/api";
import { TableSkeleton, Skeleton } from "@/components/shared/Skeleton";
import StatusBadge from "@/components/shared/StatusBadge";
import EmptyState from "@/components/shared/EmptyState";
import { toast } from "@/lib/toast";
import { displayName } from "@/lib/displayName";

// ── File history drawer ───────────────────────────────────────────────────────

function FileHistoryDrawer({
  batchFileId,
  onClose,
}: {
  batchFileId: number;
  onClose: () => void;
}) {
  const [data, setData] = useState<FileHistoryResponse | null>(null);
  const [runs, setRuns] = useState<QCHistoryRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getFileHistory(batchFileId),
      getQCHistory(batchFileId),
    ]).then(([h, r]) => { setData(h); setRuns(r); })
      .catch(() => toast.error("Failed to load file history"))
      .finally(() => setLoading(false));
  }, [batchFileId]);

  const qc = data?.activeQcResult;
  const rejectionCategoryLabel: Record<string, string> = {
    EXTRACTION_MISMATCH: "Extraction mismatch",
    DOCUMENT_ISSUE: "Document issue",
    QC_MISMATCH: "QC mismatch",
    SIGNATURE_ISSUE: "Signature issue",
    OTHER: "Other",
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50">
      <div className="flex h-full w-full max-w-[520px] flex-col overflow-y-auto bg-sunken shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-white/10 bg-sunken px-5 py-3.5">
          <div className="flex items-center gap-2">
            <History size={15} className="text-slate-400" />
            <span className="text-sm font-semibold text-white">File History</span>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
            <XCircle size={16} />
          </button>
        </div>

        {loading ? (
          <div className="p-5 space-y-3">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-10 w-full" />)}
          </div>
        ) : !data ? null : (
          <div className="flex-1 p-5 space-y-5">
            {/* File info */}
            <div className="rounded-lg border border-white/10 bg-surface px-4 py-3">
              <div className="text-sm font-medium text-white">{data.filename}</div>
              <div className="mt-1 flex items-center gap-3 text-[11px] text-slate-500">
                <span>{data.fileType}</span>
                {data.propertySetName && (
                  <>
                    <span className="text-slate-700">·</span>
                    <span>{data.propertySetName}</span>
                  </>
                )}
                <span className="text-slate-700">·</span>
                <StatusBadge status={data.status ?? ""} size="xs" />
              </div>
            </div>

            {/* Rejection language — visible to admin */}
            {qc?.finalDecision === "FAIL" && (
              <div className="rounded-lg border border-red-500/25 bg-red-950/20 px-4 py-3">
                <div className="text-xs font-semibold text-red-300 mb-1">Rejection outcome</div>
                {qc.rejectionCategory && (
                  <div className="text-[12px] text-red-200">
                    <span className="text-slate-500">Category: </span>
                    {rejectionCategoryLabel[qc.rejectionCategory] ?? qc.rejectionCategory}
                  </div>
                )}
                {qc.rejectionNote && (
                  <div className="mt-1 text-[12px] text-slate-300 leading-relaxed">{qc.rejectionNote}</div>
                )}
                {qc.reviewerNotes && (
                  <div className="mt-1 text-[12px] text-slate-400 italic">Notes: {qc.reviewerNotes}</div>
                )}
                {qc.reviewedAt && (
                  <div className="mt-1 text-[11px] text-slate-600">
                    {new Date(qc.reviewedAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </div>
                )}
              </div>
            )}

            {/* Active QC result */}
            {qc && qc.finalDecision !== "FAIL" && (
              <div className="rounded-lg border border-white/10 bg-surface px-4 py-3">
                <div className="text-xs font-semibold text-slate-400 mb-2">Active QC result</div>
                <div className="flex items-center gap-3">
                  <StatusBadge status={qc.finalDecision ?? qc.qcDecision ?? ""} size="xs" />
                  <span className="text-[12px] text-slate-400 tabular-nums">
                    {qc.passedCount} pass · {qc.failedCount} fail · {qc.totalRules} rules
                  </span>
                </div>
                {qc.processedAt && (
                  <div className="mt-1 text-[11px] text-slate-600">
                    Processed {new Date(qc.processedAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </div>
                )}
              </div>
            )}

            {/* QC run history */}
            {runs.length > 0 && (
              <div>
                <div className="mb-2 text-xs font-semibold text-slate-400">QC runs ({runs.length})</div>
                <div className="space-y-1.5">
                  {runs.map((run, i) => (
                    <div key={run.id} className={`rounded-md border px-3 py-2 text-[11px] ${run.isActive ? "border-indigo-500/25 bg-indigo-950/20" : "border-white/[0.06] bg-sunken"}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-slate-300">Run #{runs.length - i}</span>
                        <StatusBadge status={run.finalDecision ?? run.qcDecision ?? ""} size="xs" />
                      </div>
                      <div className="mt-0.5 text-slate-500 tabular-nums">
                        {run.passedCount} pass · {run.failedCount} fail · {run.totalRules} rules
                        {run.supersededAt && <span className="ml-2 text-slate-600">superseded</span>}
                        {run.isActive && <span className="ml-2 text-indigo-400">active</span>}
                      </div>
                      {run.processedAt && (
                        <div className="mt-0.5 text-slate-600">
                          {new Date(run.processedAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Event timeline */}
            {data.events.length > 0 && (
              <div>
                <div className="mb-2 text-xs font-semibold text-slate-400">Event timeline</div>
                <div className="relative border-l border-white/10 pl-4 space-y-3">
                  {data.events.map(e => (
                    <div key={e.id} className="relative">
                      <span className="absolute -left-[17px] top-1.5 h-2 w-2 rounded-full bg-slate-700 ring-2 ring-sunken" />
                      <div className="text-[11px] text-slate-400">{e.eventType.replace(/_/g, " ")}</div>
                      {e.outcome && <div className="text-[10px] text-slate-600">{e.outcome}</div>}
                      {e.occurredAt && (
                        <div className="text-[10px] text-slate-600">
                          {new Date(e.occurredAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Assign drawer ─────────────────────────────────────────────────────────────

function AssignDrawer({
  file,
  appraisals,
  batchId,
  onClose,
  onSuccess,
}: {
  file: BatchFile;
  appraisals: BatchFile[];
  batchId: number;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [selected, setSelected] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [mismatch, setMismatch] = useState<string | null>(null);

  async function handleAssign(force = false) {
    if (!selected) return;
    setBusy(true);
    try {
      await assignFileToAppraisal(batchId, file.id, selected, force);
      toast.info("File assigned", "Run Re-QC on the appraisal to include this document.");
      onSuccess();
    } catch (e) {
      if (e instanceof AddressMismatchError) {
        setMismatch(e.message);
      } else {
        toast.error("Assignment failed", String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50">
      <div className="flex h-full w-full max-w-[460px] flex-col bg-sunken shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-white/10 bg-sunken px-5 py-3.5">
          <div className="flex items-center gap-2">
            <Link2 size={15} className="text-orange-400" />
            <span className="text-sm font-semibold text-white">Assign to Appraisal</span>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
            <XCircle size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* File being assigned */}
          <div className="rounded-lg border border-orange-500/25 bg-orange-950/20 px-4 py-3">
            <div className="text-[10px] font-medium uppercase tracking-wide text-orange-400 mb-1">Unassigned file</div>
            <div className="text-sm font-medium text-white truncate">{file.filename}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">{file.fileType}</div>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Select appraisal to link this file to
            </label>
            {appraisals.length === 0 ? (
              <div className="rounded-md border border-white/10 bg-sunken px-3 py-2 text-[12px] text-slate-500">
                No appraisals found in this batch.
              </div>
            ) : (
              <select
                value={selected}
                onChange={e => { setSelected(e.target.value === "" ? "" : Number(e.target.value)); setMismatch(null); }}
                className="w-full rounded-md border border-white/10 bg-sunken px-3 py-2 text-sm text-slate-200 focus:border-orange-500/50 focus:outline-none"
              >
                <option value="">— choose an appraisal —</option>
                {appraisals.map(a => (
                  <option key={a.id} value={a.id}>
                    {a.filename}{a.orderId ? ` (Order ${a.orderId})` : ""}
                  </option>
                ))}
              </select>
            )}
          </div>

          {mismatch && (
            <div className="rounded-lg border border-red-500/25 bg-red-950/20 px-4 py-3">
              <div className="text-[10px] font-medium uppercase tracking-wide text-red-400 mb-1">Content mismatch</div>
              <div className="text-[12px] leading-relaxed text-red-200">{mismatch}</div>
            </div>
          )}

          <div className="rounded-md border border-white/[0.06] bg-sunken px-3 py-2.5 text-[11px] text-slate-500 leading-relaxed">
            After assigning, click <strong className="text-slate-400">Re-QC</strong> on the appraisal row to re-run quality checks with this document included.
          </div>
        </div>

        <div className="border-t border-white/10 p-4 flex gap-2">
          {mismatch ? (
            <button
              onClick={() => handleAssign(true)}
              disabled={busy}
              className="flex-1 rounded-md border border-red-500/40 bg-red-950/40 py-2 text-sm font-medium text-red-200 transition-colors hover:bg-red-950/70 disabled:opacity-40"
            >
              {busy ? "Assigning…" : "Assign anyway"}
            </button>
          ) : (
            <button
              onClick={() => handleAssign(false)}
              disabled={!selected || busy}
              className="flex-1 rounded-md border border-orange-500/40 bg-orange-950/40 py-2 text-sm font-medium text-orange-200 transition-colors hover:bg-orange-950/70 disabled:opacity-40"
            >
              {busy ? "Assigning…" : "Assign"}
            </button>
          )}
          <button
            onClick={onClose}
            className="rounded-md border border-white/10 bg-surface px-4 py-2 text-sm text-slate-400 transition-colors hover:text-white"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Reclassify drawer ─────────────────────────────────────────────────────────

const RECLASSIFY_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "APPRAISAL_XML", label: "Appraisal XML (MISMO)" },
  { value: "APPRAISAL",    label: "Appraisal (PDF)" },
  { value: "ENGAGEMENT",   label: "Engagement Letter" },
  { value: "CONTRACT",     label: "Contract" },
];

function ReclassifyDrawer({
  file,
  batchId,
  onClose,
  onSuccess,
}: {
  file: BatchFile;
  batchId: number;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [selected, setSelected] = useState<string>("");
  const [busy, setBusy] = useState(false);

  async function handleReclassify() {
    if (!selected) return;
    setBusy(true);
    try {
      await reclassifyBatchFile(batchId, file.id, selected);
      toast.info("File reclassified", "Run Re-QC on the appraisal to apply the change.");
      onSuccess();
    } catch (e) {
      toast.error("Reclassify failed", String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50">
      <div className="flex h-full w-full max-w-[420px] flex-col bg-sunken shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-white/10 bg-sunken px-5 py-3.5">
          <div className="flex items-center gap-2">
            <RotateCcw size={14} className="text-slate-400" />
            <span className="text-sm font-semibold text-white">Reclassify File</span>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
            <XCircle size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          <div className="rounded-lg border border-white/10 bg-surface px-4 py-3">
            <div className="text-sm font-medium text-white truncate">{file.filename}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              Current type: <span className="text-slate-300">{fileTypeLabel(file.fileType)}</span>
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">New document type</label>
            <select
              value={selected}
              onChange={e => setSelected(e.target.value)}
              className="w-full rounded-md border border-white/10 bg-sunken px-3 py-2 text-sm text-slate-200 focus:border-indigo-500/50 focus:outline-none"
            >
              <option value="">— choose a type —</option>
              {RECLASSIFY_OPTIONS.filter(o => o.value !== file.fileType).map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <div className="rounded-md border border-white/[0.06] bg-sunken px-3 py-2.5 text-[11px] text-slate-500 leading-relaxed">
            Use this when intake misclassified a file — most commonly a MISMO XML uploaded outside the <code className="text-slate-400">appraisal/</code> folder that was tagged as Contract. After reclassifying, run Re-QC.
          </div>
        </div>

        <div className="border-t border-white/10 p-4 flex gap-2">
          <button
            onClick={handleReclassify}
            disabled={!selected || busy}
            className="flex-1 rounded-md border border-indigo-500/30 bg-indigo-950/30 py-2 text-sm font-medium text-indigo-200 transition-colors hover:bg-indigo-950/60 disabled:opacity-40"
          >
            {busy ? "Reclassifying…" : "Reclassify"}
          </button>
          <button
            onClick={onClose}
            className="rounded-md border border-white/10 bg-surface px-4 py-2 text-sm text-slate-400 transition-colors hover:text-white"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fileTypeLabel(t: BatchFile["fileType"]): string {
  switch (t) {
    case "APPRAISAL":     return "Appraisal";
    case "APPRAISAL_XML": return "Appraisal XML";
    case "ENGAGEMENT":    return "Engagement";
    case "CONTRACT":      return "Contract";
  }
}

function fileTypeBadgeClass(t: BatchFile["fileType"]): string {
  switch (t) {
    case "APPRAISAL":     return "bg-indigo-950/50 text-indigo-300 border border-indigo-500/25";
    case "APPRAISAL_XML": return "bg-violet-950/50 text-violet-300 border border-violet-500/25";
    case "ENGAGEMENT":    return "bg-slate-800/60 text-slate-300 border border-white/10";
    case "CONTRACT":      return "bg-slate-800/60 text-slate-400 border border-white/10";
  }
}

// ── Property set section ──────────────────────────────────────────────────────

function PropertySetSection({
  set,
  allAppraisals,
  resultMap,
  onReQC,
  onHistory,
  onAssign,
  onReclassify,
  reQcBusy,
  isUnlinkedPool = false,
}: {
  set: PropertySet;
  allAppraisals: BatchFile[];
  resultMap: Map<number, QCResult>;
  onReQC: (fileId: number) => void;
  onHistory: (fileId: number) => void;
  onAssign: (file: BatchFile) => void;
  onReclassify: (file: BatchFile) => void;
  reQcBusy: Set<number>;
  /** True for a folder with no appraisal — a pool of documents awaiting assignment,
   * never an order (fixes documents forking pseudo-orders like "Order EngagementLetter 2"). */
  isUnlinkedPool?: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const appraisals = set.files.filter(f => f.fileType === "APPRAISAL");
  const supporting = set.files.filter(f => f.fileType !== "APPRAISAL");

  return (
    <div className={`overflow-hidden rounded-xl border bg-surface ${isUnlinkedPool ? "border-orange-500/25" : "border-white/10"}`}>
      {/* Set header */}
      <div className={`flex w-full items-center justify-between border-b px-5 py-3 text-left ${isUnlinkedPool ? "border-orange-500/15 bg-orange-950/10" : "border-white/10"}`}>
        <button
          onClick={() => setExpanded(e => !e)}
          className="flex flex-1 items-center gap-2.5 text-left"
        >
          {isUnlinkedPool
            ? <Link2 size={15} className="text-orange-400 shrink-0" />
            : <Building2 size={15} className="text-slate-400 shrink-0" />}
          <span className="font-medium text-white">
            {isUnlinkedPool ? `Unlinked documents${set.setName ? ` — "${set.setName}"` : ""}` : (set.setName ?? "All files")}
          </span>
          <span className="rounded-full border border-white/10 bg-sunken px-2 py-0.5 text-[10px] text-slate-500">
            {set.fileCount} file{set.fileCount !== 1 ? "s" : ""}
          </span>
          {set.errorCount > 0 && (
            <span className="rounded-full border border-red-500/25 bg-red-950/30 px-2 py-0.5 text-[10px] text-red-300">
              {set.errorCount} error{set.errorCount !== 1 ? "s" : ""}
            </span>
          )}
          {set.pendingCount > 0 && (
            <span className="rounded-full border border-amber-500/25 bg-amber-950/30 px-2 py-0.5 text-[10px] text-amber-300">
              {set.pendingCount} pending
            </span>
          )}
          {(set.needsAssignmentCount ?? 0) > 0 && (
            <span className="rounded-full border border-orange-500/30 bg-orange-950/30 px-2 py-0.5 text-[10px] text-orange-300">
              {set.needsAssignmentCount} unassigned
            </span>
          )}
          {set.completedCount > 0 && (
            <span className="rounded-full border border-green-900/40 bg-green-950/30 px-2 py-0.5 text-[10px] text-green-300">
              {set.completedCount} completed
            </span>
          )}
        </button>
        <div className="flex items-center gap-2">
          {set.orderId && (
            <Link
              href={`/admin/orders/${set.orderId}`}
              onClick={e => e.stopPropagation()}
              title="View this order's own status, documents, and batch history"
              className="rounded-full border border-indigo-500/25 bg-indigo-950/20 px-2.5 py-0.5 text-[10px] font-medium text-indigo-300 transition-colors hover:bg-indigo-950/50"
            >
              View order ↗
            </Link>
          )}
          <button onClick={() => setExpanded(e => !e)}>
            {expanded ? <ChevronUp size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
          </button>
        </div>
      </div>

      {expanded && isUnlinkedPool && (
        <div className="border-b border-orange-500/10 bg-orange-950/5 px-5 py-2.5 text-[11px] leading-relaxed text-orange-300/80">
          No appraisal was found for this group — these are not an order, just documents awaiting assignment.
          Use <strong className="text-orange-200">Assign</strong> on each row to link it to the correct appraisal below.
        </div>
      )}

      {expanded && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/[0.06] text-left text-[11px] uppercase tracking-wide text-slate-600">
              <th className="px-5 py-2.5 font-medium">File</th>
              <th className="px-4 py-2.5 font-medium">Type</th>
              <th className="px-4 py-2.5 font-medium">QC status</th>
              <th className="px-4 py-2.5 font-medium">Issues / Review / Clear</th>
              <th className="px-4 py-2.5 font-medium">Rejection</th>
              <th className="px-4 py-2.5 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {[...appraisals, ...supporting].map(f => {
              const qc = resultMap.get(f.id);
              const hasIssues = (qc?.failedCount ?? 0) > 0;
              const isAppraisal = f.fileType === "APPRAISAL";
              const needsAssign = f.status === "NEEDS_ASSIGNMENT";
              const busy = reQcBusy.has(f.id);
              return (
                <tr
                  key={f.id}
                  className={`transition-colors hover:bg-white/[0.025] ${needsAssign ? "bg-orange-950/10" : ""}`}
                >
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${
                        needsAssign        ? "bg-orange-400" :
                        f.status === "ERROR" ? "bg-red-400" :
                        hasIssues          ? "bg-red-400" :
                        qc?.finalDecision === "PASS" ? "bg-green-400" :
                        qc                 ? "bg-amber-400" : "bg-slate-600"
                      }`} />
                      <span className="truncate font-medium text-slate-200 max-w-[260px]" title={f.filename}>
                        {f.filename}
                      </span>
                    </div>
                    {f.orderId && <div className="ml-4 mt-0.5 text-[11px] text-slate-600">Order {f.orderId}</div>}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${fileTypeBadgeClass(f.fileType)}`}>
                      {fileTypeLabel(f.fileType)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {qc ? (
                      <StatusBadge status={qc.finalDecision ?? qc.qcDecision} size="xs" />
                    ) : needsAssign ? (
                      <StatusBadge status="NEEDS_ASSIGNMENT" size="xs" />
                    ) : (
                      <span className="text-[11px] text-slate-600">{f.status?.replace(/_/g, " ") ?? "—"}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {qc ? (
                      <span className="flex items-center gap-2 tabular-nums text-[12px]">
                        <span className={qc.failedCount > 0 ? "text-red-300" : "text-slate-600"}>{qc.failedCount}</span>
                        <span className="text-slate-600">/</span>
                        <span className={qc.verifyCount > 0 ? "text-amber-300" : "text-slate-600"}>{qc.verifyCount}</span>
                        <span className="text-slate-600">/</span>
                        <span className="text-green-300">{qc.passedCount}</span>
                      </span>
                    ) : <span className="text-slate-600 text-[12px]">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    {qc?.finalDecision === "FAIL" && (
                      <div className="text-[11px]">
                        <span className="text-red-300">Rejected</span>
                        {qc.rejectionCategory && (
                          <div className="text-slate-500 mt-0.5">{qc.rejectionCategory.replace(/_/g, " ").toLowerCase()}</div>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      {/* Assign — for unmatched supporting files */}
                      {needsAssign && (
                        <button
                          onClick={() => onAssign(f)}
                          title="Assign to an appraisal"
                          className="inline-flex h-7 items-center gap-1 rounded border border-orange-500/30 bg-orange-950/30 px-2 text-[11px] text-orange-300 transition-colors hover:bg-orange-950/60"
                        >
                          <Link2 size={10} /> Assign
                        </button>
                      )}
                      {/* Reclassify — available on all supporting files */}
                      {!isAppraisal && (
                        <button
                          onClick={() => onReclassify(f)}
                          title="Change document type"
                          className="inline-flex h-7 items-center gap-1 rounded border border-white/10 bg-sunken px-2 text-[11px] text-slate-500 transition-colors hover:text-slate-200"
                        >
                          <RotateCcw size={10} /> Reclassify
                        </button>
                      )}
                      {/* Re-QC — only appraisal files can be re-run */}
                      {isAppraisal && (
                        <button
                          onClick={() => onReQC(f.id)}
                          disabled={busy}
                          title="Re-run QC for this file only"
                          className="inline-flex h-7 items-center gap-1 rounded border border-indigo-500/25 bg-indigo-950/30 px-2 text-[11px] text-indigo-300 transition-colors hover:bg-indigo-950/60 disabled:opacity-40"
                        >
                          {busy ? <RefreshCw size={10} className="animate-spin" /> : <Play size={10} />}
                          Re-QC
                        </button>
                      )}
                      {/* History */}
                      <button
                        onClick={() => onHistory(f.id)}
                        title="View file history"
                        className="inline-flex h-7 items-center gap-1 rounded border border-white/10 bg-sunken px-2 text-[11px] text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white"
                      >
                        <History size={10} /> History
                      </button>
                      {/* Rules link */}
                      {qc && (
                        <Link
                          href={`/qc-review?id=${qc.id}`}
                          className="inline-flex h-7 items-center rounded border border-white/10 bg-sunken px-2 text-[11px] text-slate-400 transition-colors hover:text-indigo-300"
                        >
                          Rules ↗
                        </Link>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function BatchDetailPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [batch, setBatch]           = useState<Batch | null>(null);
  const [results, setResults]       = useState<QCResult[]>([]);
  const [loading, setLoading]       = useState(true);
  const [historyFileId, setHistoryFileId] = useState<number | null>(null);
  const [assignFile, setAssignFile] = useState<BatchFile | null>(null);
  const [reclassifyFile, setReclassifyFile] = useState<BatchFile | null>(null);
  const [reQcBusy, setReQcBusy]     = useState<Set<number>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [b, qc] = await Promise.all([
        getBatchById(id),
        getQCResults(id).catch(() => [] as QCResult[]),
      ]);
      setBatch(b);
      setResults(qc);
    } catch {
      toast.error("Failed to load batch detail");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    const t = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(t);
  }, [load]);

  const resultMap = new Map(results.map(r => [r.batchFile?.id, r]));
  const files = batch?.files ?? [];

  const totalFiles = files.length;
  const passed  = results.filter(r => r.finalDecision === "PASS").length;
  const failed  = results.filter(r => r.finalDecision === "FAIL").length;
  const pending = results.filter(r => !r.finalDecision && r.qcDecision !== "AUTO_PASS").length;

  const propertySets = batch?.propertySets ?? [];
  // A group with no appraisal is a pool of unlinked documents, never an order — a
  // folder like "4" that only holds engagement letters must not render as
  // "Order 4" (see PropertySetSection's isUnlinkedPool).
  const orderSets    = propertySets.filter(ps => ps.files.some(f => f.fileType === "APPRAISAL"));
  const unlinkedSets = propertySets.filter(ps => !ps.files.some(f => f.fileType === "APPRAISAL"));
  const isMultiSet   = (batch?.setCount ?? 0) > 1;
  const needsAssignmentTotal = batch?.needsAssignmentCount ?? 0;

  // All appraisals across the batch — shown in the assign dropdown.
  const allAppraisals = files.filter(f => f.fileType === "APPRAISAL");

  // Re-QC is order-scoped: QC is a per-Order action now. Resolve the file's owning Order
  // and run QC for that order (the whole batch is never QC'd).
  async function handleReQC(fileId: number) {
    const file = files.find(f => f.id === fileId);
    const orderId = file?.resolvedOrderId;
    if (!orderId) {
      toast.error("Re-QC unavailable", "This file isn't linked to an order yet — assign it first.");
      return;
    }
    setReQcBusy(s => new Set([...s, fileId]));
    try {
      await processOrderQC(orderId);
      toast.info("Re-QC started", "Results will update when processing completes.");
      window.setTimeout(() => { void load(); }, 2000);
    } catch (e) {
      toast.error("Re-QC failed", String(e));
    } finally {
      setReQcBusy(s => { const n = new Set(s); n.delete(fileId); return n; });
    }
  }

  return (
    <div className="w-full max-w-[1800px] p-6 lg:p-8">
      {/* Breadcrumb */}
      <nav className="mb-4 flex items-center gap-1.5 text-xs text-slate-500">
        <Link href="/admin/batches" className="inline-flex items-center gap-1 transition-colors hover:text-slate-300">
          <ArrowLeft size={12} /> Batches
        </Link>
        <ChevronRight size={12} className="text-slate-600" />
        <span className="text-slate-300 truncate max-w-[320px]">
          {loading ? "Loading…" : batch?.parentBatchId ?? `Batch #${id}`}
        </span>
      </nav>

      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-muted">
            <Package size={18} className="text-slate-400" />
          </div>
          <div className="min-w-0">
            {loading ? (
              <Skeleton className="h-6 w-64" />
            ) : (
              <h1 className="font-mono text-lg font-semibold text-white">{batch?.parentBatchId ?? `Batch #${id}`}</h1>
            )}
            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              {batch?.client && <span>{batch.client.name}</span>}
              {isMultiSet && (
                <>
                  <span className="text-slate-700">·</span>
                  <span className="text-slate-400">{batch?.setCount} orders</span>
                </>
              )}
              {batch?.assignedReviewer && (
                <>
                  <span className="text-slate-700">·</span>
                  <span className="flex items-center gap-1">
                    <UserCheck size={11} className="text-slate-600" />
                    {batch.assignedReviewer.fullName ?? displayName(batch.assignedReviewer.username)}
                  </span>
                </>
              )}
              {batch?.createdAt && (
                <>
                  <span className="text-slate-700">·</span>
                  <span>{new Date(batch.createdAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {batch?.status && <StatusBadge status={batch.status} />}
          <button
            onClick={() => load()}
            className="flex h-8 items-center gap-1.5 rounded-md border border-white/10 bg-surface px-3 text-xs text-slate-400 transition-colors hover:text-white"
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </header>

      {/* Order-status rollup — the honest per-order breakdown. The batch status above is
          only the intake/processing state; QC, review and completion are tracked per order. */}
      {batch?.orderStatusRollup && Object.keys(batch.orderStatusRollup).length > 0 && (
        <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-slate-500">
          <span className="text-slate-400">{batch.orderCount ?? 0} order{(batch.orderCount ?? 0) === 1 ? "" : "s"}</span>
          {Object.entries(batch.orderStatusRollup).map(([status, count]) => (
            <span key={status} className="inline-flex items-center gap-1.5">
              <span className="text-slate-700">·</span>
              <StatusBadge status={status} size="xs" />
              <span className="tabular-nums text-slate-400">{count}</span>
            </span>
          ))}
        </div>
      )}

      {/* Needs-assignment alert */}
      {needsAssignmentTotal > 0 && (
        <div className="mb-5 flex items-start gap-2.5 rounded-lg border border-orange-500/30 bg-orange-950/20 px-4 py-3 text-sm text-orange-200">
          <Link2 size={15} className="mt-0.5 shrink-0 text-orange-400" />
          <div>
            <div className="font-semibold">
              {needsAssignmentTotal} file{needsAssignmentTotal !== 1 ? "s" : ""} need manual assignment
            </div>
            <div className="mt-0.5 text-[12px] leading-relaxed opacity-90">
              These supporting files could not be linked automatically — either no order in this batch matches
              them, or more than one plausible order does. Click <strong>Assign</strong> on each highlighted row,
              pair it with the correct appraisal, then run Re-QC.
            </div>
          </div>
        </div>
      )}

      {/* Intake warnings */}
      {batch?.intakeWarnings && (
        <div className="mb-5 flex items-start gap-2.5 rounded-lg border border-amber-500/25 bg-amber-950/20 px-4 py-3 text-sm text-amber-200">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Intake warnings</div>
            <div className="mt-1 text-[12px] leading-relaxed opacity-90 whitespace-pre-line">{batch.intakeWarnings}</div>
          </div>
        </div>
      )}

      {/* Stats row */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Files"   value={loading ? "—" : String(totalFiles)} icon={FileText} />
        <Stat label="Passed"  value={loading ? "—" : String(passed)}     icon={CheckCircle2} tone="text-green-300" />
        <Stat label="Failed"  value={loading ? "—" : String(failed)}     icon={AlertCircle}  tone="text-red-300" />
        <Stat label="Pending" value={loading ? "—" : String(pending)}    icon={Clock}        tone="text-amber-300" />
      </div>

      {/* File sections */}
      {loading ? (
        <div className="rounded-xl border border-white/10 bg-surface p-4">
          <TableSkeleton rows={6} cols={5} />
        </div>
      ) : files.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-surface">
          <EmptyState icon={FileText} title="No files" description="This batch has no attached files." />
        </div>
      ) : isMultiSet && propertySets.length > 0 ? (
        <div className="space-y-4">
          {orderSets.map((ps, i) => (
            <PropertySetSection
              key={ps.orderId ?? ps.setName ?? i}
              set={ps}
              allAppraisals={allAppraisals}
              resultMap={resultMap}
              onReQC={handleReQC}
              onHistory={setHistoryFileId}
              onAssign={setAssignFile}
              onReclassify={setReclassifyFile}
              reQcBusy={reQcBusy}
            />
          ))}
          {unlinkedSets.length > 0 && (
            <div className="space-y-3 pt-2">
              <div className="text-xs font-medium uppercase tracking-wide text-orange-400/80">
                Unlinked documents ({unlinkedSets.reduce((n, ps) => n + ps.fileCount, 0)})
              </div>
              {unlinkedSets.map((ps, i) => (
                <PropertySetSection
                  key={`unlinked-${ps.setName ?? i}`}
                  set={ps}
                  allAppraisals={allAppraisals}
                  resultMap={resultMap}
                  onReQC={handleReQC}
                  onHistory={setHistoryFileId}
                  onAssign={setAssignFile}
                  onReclassify={setReclassifyFile}
                  reQcBusy={reQcBusy}
                  isUnlinkedPool
                />
              ))}
            </div>
          )}
        </div>
      ) : (
        <PropertySetSection
          set={propertySets[0] ?? {
            setName: null, files, fileCount: files.length,
            completedCount: 0, errorCount: 0, pendingCount: 0, needsAssignmentCount: 0,
          }}
          allAppraisals={allAppraisals}
          resultMap={resultMap}
          onReQC={handleReQC}
          onHistory={setHistoryFileId}
          onAssign={setAssignFile}
          onReclassify={setReclassifyFile}
          reQcBusy={reQcBusy}
        />
      )}

      {/* Error message */}
      {batch?.errorMessage && (
        <div className="mt-5 flex items-start gap-2.5 rounded-lg border border-red-500/25 bg-red-950/20 px-4 py-3 text-sm text-red-200">
          <AlertCircle size={15} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Processing error</div>
            <div className="mt-1 font-mono text-[11px] leading-relaxed">{batch.errorMessage}</div>
          </div>
        </div>
      )}

      {/* File history drawer */}
      {historyFileId !== null && (
        <FileHistoryDrawer
          key={historyFileId}
          batchFileId={historyFileId}
          onClose={() => setHistoryFileId(null)}
        />
      )}

      {/* Assign drawer */}
      {assignFile !== null && (
        <AssignDrawer
          key={assignFile.id}
          file={assignFile}
          appraisals={allAppraisals}
          batchId={id}
          onClose={() => setAssignFile(null)}
          onSuccess={() => { setAssignFile(null); void load(); }}
        />
      )}

      {/* Reclassify drawer */}
      {reclassifyFile !== null && (
        <ReclassifyDrawer
          key={reclassifyFile.id}
          file={reclassifyFile}
          batchId={id}
          onClose={() => setReclassifyFile(null)}
          onSuccess={() => { setReclassifyFile(null); void load(); }}
        />
      )}
    </div>
  );
}

function Stat({ label, value, icon: Icon, tone = "text-white" }: {
  label: string; value: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  tone?: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-surface p-4">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-500">
        <Icon size={13} /> {label}
      </div>
      <div className={`text-2xl font-semibold tabular-nums ${tone}`}>{value}</div>
    </div>
  );
}

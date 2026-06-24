"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, ChevronRight, Package, FileText, CheckCircle2,
  AlertCircle, Clock, UserCheck, AlertTriangle, RefreshCw,
  Play, History, ChevronDown, ChevronUp, XCircle, Building2,
} from "lucide-react";
import {
  getBatchById, getQCResults, processQCFiles, getFileHistory,
  getQCHistory,
  type Batch, type QCResult, type PropertySet, type FileHistoryResponse,
  type QCHistoryRun,
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
    setLoading(true);
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
      <div className="flex h-full w-full max-w-[520px] flex-col overflow-y-auto bg-[#0E1318] shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-white/10 bg-[#0E1318] px-5 py-3.5">
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
            <div className="rounded-lg border border-white/10 bg-[#11161C] px-4 py-3">
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
              <div className="rounded-lg border border-white/10 bg-[#11161C] px-4 py-3">
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
                    <div key={run.id} className={`rounded-md border px-3 py-2 text-[11px] ${run.isActive ? "border-indigo-500/25 bg-indigo-950/20" : "border-white/[0.06] bg-[#0B0F14]"}`}>
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
                      <span className="absolute -left-[17px] top-1.5 h-2 w-2 rounded-full bg-slate-700 ring-2 ring-[#0E1318]" />
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

// ── Property set section ──────────────────────────────────────────────────────

function PropertySetSection({
  set,
  resultMap,
  batchId,
  onReQC,
  onHistory,
  reQcBusy,
}: {
  set: PropertySet;
  resultMap: Map<number, QCResult>;
  batchId: number;
  onReQC: (fileId: number) => void;
  onHistory: (fileId: number) => void;
  reQcBusy: Set<number>;
}) {
  const [expanded, setExpanded] = useState(true);
  const appraisals = set.files.filter(f => f.fileType === "APPRAISAL");
  const supporting = set.files.filter(f => f.fileType !== "APPRAISAL");

  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-[#11161C]">
      {/* Set header */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="flex w-full items-center justify-between border-b border-white/10 px-5 py-3 text-left"
      >
        <div className="flex items-center gap-2.5">
          <Building2 size={15} className="text-slate-400 shrink-0" />
          <span className="font-medium text-white">
            {set.setName ?? "All files"}
          </span>
          <span className="rounded-full border border-white/10 bg-[#0B0F14] px-2 py-0.5 text-[10px] text-slate-500">
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
          {set.completedCount > 0 && (
            <span className="rounded-full border border-green-900/40 bg-green-950/30 px-2 py-0.5 text-[10px] text-green-300">
              {set.completedCount} completed
            </span>
          )}
        </div>
        {expanded ? <ChevronUp size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
      </button>

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
              const busy = reQcBusy.has(f.id);
              return (
                <tr key={f.id} className="transition-colors hover:bg-white/[0.025]">
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${
                        f.status === "ERROR" ? "bg-red-400" :
                        hasIssues ? "bg-red-400" :
                        qc?.finalDecision === "PASS" ? "bg-green-400" :
                        qc ? "bg-amber-400" : "bg-slate-600"
                      }`} />
                      <span className="truncate font-medium text-slate-200 max-w-[260px]" title={f.filename}>
                        {f.filename}
                      </span>
                    </div>
                    {f.orderId && <div className="ml-4 mt-0.5 text-[11px] text-slate-600">Order {f.orderId}</div>}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      isAppraisal ? "bg-indigo-950/50 text-indigo-300 border border-indigo-500/25" :
                      f.fileType === "ENGAGEMENT" ? "bg-slate-800/60 text-slate-300 border border-white/10" :
                      "bg-slate-800/60 text-slate-400 border border-white/10"
                    }`}>
                      {f.fileType === "APPRAISAL" ? "Appraisal" : f.fileType === "ENGAGEMENT" ? "Engagement" : "Contract"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {qc ? (
                      <StatusBadge status={qc.finalDecision ?? qc.qcDecision} size="xs" />
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
                        className="inline-flex h-7 items-center gap-1 rounded border border-white/10 bg-[#0B0F14] px-2 text-[11px] text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white"
                      >
                        <History size={10} /> History
                      </button>
                      {/* Rules link */}
                      {qc && (
                        <Link
                          href={`/qc-review?id=${qc.id}`}
                          className="inline-flex h-7 items-center rounded border border-white/10 bg-[#0B0F14] px-2 text-[11px] text-slate-400 transition-colors hover:text-indigo-300"
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
  const [batch, setBatch]         = useState<Batch | null>(null);
  const [results, setResults]     = useState<QCResult[]>([]);
  const [loading, setLoading]     = useState(true);
  const [historyFileId, setHistoryFileId] = useState<number | null>(null);
  const [reQcBusy, setReQcBusy]   = useState<Set<number>>(new Set());

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
  const isMultiSet   = (batch?.setCount ?? 0) > 1;

  async function handleReQC(fileId: number) {
    setReQcBusy(s => new Set([...s, fileId]));
    try {
      await processQCFiles(id, [fileId]);
      toast.info("Re-QC started", "Results will update when processing completes.");
      // Refresh after short delay to pick up the QC_PROCESSING status
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
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-[#161B22]">
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
                  <span className="text-slate-400">{batch?.setCount} property sets</span>
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
            className="flex h-8 items-center gap-1.5 rounded-md border border-white/10 bg-[#11161C] px-3 text-xs text-slate-400 transition-colors hover:text-white"
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </header>

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
        <div className="rounded-xl border border-white/10 bg-[#11161C] p-4">
          <TableSkeleton rows={6} cols={5} />
        </div>
      ) : files.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-[#11161C]">
          <EmptyState icon={FileText} title="No files" description="This batch has no attached files." />
        </div>
      ) : isMultiSet && propertySets.length > 0 ? (
        /* Multi-set: one card per property set */
        <div className="space-y-4">
          {propertySets.map((ps, i) => (
            <PropertySetSection
              key={ps.setName ?? i}
              set={ps}
              resultMap={resultMap}
              batchId={id}
              onReQC={handleReQC}
              onHistory={setHistoryFileId}
              reQcBusy={reQcBusy}
            />
          ))}
        </div>
      ) : (
        /* Single-set / flat: single card */
        <PropertySetSection
          set={propertySets[0] ?? { setName: null, files, fileCount: files.length, completedCount: 0, errorCount: 0, pendingCount: 0 }}
          resultMap={resultMap}
          batchId={id}
          onReQC={handleReQC}
          onHistory={setHistoryFileId}
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
          batchFileId={historyFileId}
          onClose={() => setHistoryFileId(null)}
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
    <div className="rounded-xl border border-white/10 bg-[#11161C] p-4">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-500">
        <Icon size={13} /> {label}
      </div>
      <div className={`text-2xl font-semibold tabular-nums ${tone}`}>{value}</div>
    </div>
  );
}

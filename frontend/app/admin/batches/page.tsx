"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  Search, Plus, RefreshCw, ChevronLeft, ChevronRight,
  FileStack, Clock3, CheckCircle2, Play, UserPlus, SlidersHorizontal, XCircle,
} from "lucide-react";
import type { ComponentType } from "react";
import {
  getAdminBatches, processQC, assignReviewer, deleteBatch,
  reconcileStuckBatches, cancelQC, getAdminDashboard, getAllUsers,
  type Batch, type User, type QCModelSelection,
} from "@/lib/api";
import { removeJob } from "@/lib/jobs";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import UploadModal from "@/components/admin/UploadModal";
import { BatchRow } from "@/components/admin/BatchRow";
import { BatchRecoveryDrawer } from "@/components/admin/BatchRecoveryDrawer";
import { TableSkeleton } from "@/components/shared/Skeleton";
import EmptyState from "@/components/shared/EmptyState";
import { toast } from "@/lib/toast";
import { useBatchPolling } from "@/hooks/useBatchPolling";

const STATUSES = [
  "", "UPLOADED", "VALIDATING", "VALIDATION_FAILED",
  "QC_PROCESSING", "REVIEW_PENDING", "IN_REVIEW", "COMPLETED", "ERROR",
];

const MODEL_OPTIONS: Record<QCModelSelection["provider"], { label: string; text: string[]; vision: string[] }> = {
  ollama: { label: "Ollama", text: ["llava:7b", "llava:13b"], vision: ["llava:7b", "llava:13b"] },
};

type ReconcileResult = {
  stuckFound: number; retried: number; abandoned: number; pythonHealthy: boolean; message: string;
};

function batchLog(event: string, payload?: unknown) {
  if (process.env.NODE_ENV !== "production") console.log(`[BatchesPage] ${event}`, payload ?? "");
}

// ── Pill summary ──────────────────────────────────────────────────────────────
function SummaryPill({ icon: Icon, label, value, tone }: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string; value: number;
  tone: "slate" | "blue" | "indigo" | "amber" | "green";
}) {
  const tones = {
    slate: "border-white/10 bg-[#11161C] text-slate-300",
    blue:  "border-blue-900/50 bg-blue-950/30 text-blue-200",
    indigo:"border-blue-500/25 bg-blue-950/30 text-blue-200",
    amber: "border-amber-900/50 bg-amber-950/30 text-amber-200",
    green: "border-green-900/50 bg-green-950/30 text-green-200",
  };
  return (
    <div className={`flex h-14 items-center gap-3 rounded-lg border px-3 ${tones[tone]}`}>
      <Icon size={16} className="shrink-0 opacity-80" />
      <div className="min-w-0">
        <div className="text-lg font-semibold leading-none tabular-nums">{value}</div>
        <div className="mt-1 truncate text-[11px] uppercase tracking-wide opacity-70">{label}</div>
      </div>
    </div>
  );
}

// ── Reconcile summary ─────────────────────────────────────────────────────────
function RecoveryMetric({ label, value, tone }: { label: string; value: number | string; tone: "slate" | "amber" | "blue" | "green" | "red" }) {
  const tones = {
    slate: "border-white/10 bg-[#0B0F14]/70 text-slate-300",
    amber: "border-amber-900/50 bg-amber-950/30 text-amber-200",
    blue:  "border-blue-900/50 bg-blue-950/30 text-blue-200",
    green: "border-green-900/50 bg-green-950/30 text-green-200",
    red:   "border-red-900/50 bg-red-950/30 text-red-200",
  };
  return (
    <div className={`rounded-md border px-3 py-2 ${tones[tone]}`}>
      <div className="text-sm font-semibold tabular-nums">{value}</div>
      <div className="mt-0.5 text-[10px] uppercase tracking-wide opacity-70">{label}</div>
    </div>
  );
}

function ReconcileSummary({ result, onDismiss }: { result: ReconcileResult; onDismiss: () => void }) {
  const changed = result.retried + result.abandoned;
  return (
    <div className="mb-4 rounded-lg border border-white/10 bg-[#11161C] p-4 shadow-[0_12px_32px_rgba(0,0,0,0.18)]">
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border ${changed > 0 ? "border-amber-800/50 bg-amber-950/40 text-amber-300" : "border-green-800/50 bg-green-950/30 text-green-300"}`}>
          <RefreshCw size={14} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-slate-200">Reconciliation result</div>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">{result.message}</p>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <RecoveryMetric label="Stuck found" value={result.stuckFound} tone={result.stuckFound > 0 ? "amber" : "slate"} />
            <RecoveryMetric label="Retried"     value={result.retried}    tone={result.retried > 0    ? "blue"  : "slate"} />
            <RecoveryMetric label="Abandoned"   value={result.abandoned}  tone={result.abandoned > 0  ? "red"   : "slate"} />
            <RecoveryMetric label="QC service"  value={result.pythonHealthy ? "Healthy" : "Needs check"} tone={result.pythonHealthy ? "green" : "red"} />
          </div>
        </div>
        <button onClick={onDismiss} className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-white/[0.04] hover:text-slate-300" aria-label="Dismiss reconciliation result">
          <XCircle size={14} />
        </button>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function BatchesPage() {
  const [batches, setBatches]         = useState<Batch[]>([]);
  const [reviewers, setReviewers]     = useState<User[]>([]);
  const [page, setPage]               = useState(() => {
    if (typeof window === "undefined") return 0;
    const parsed = Number(new URLSearchParams(window.location.search).get("page") ?? 0);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : 0;
  });
  const [totalPages, setTotalPages]   = useState(1);
  const [totalElements, setTotalElements] = useState(0);
  const [statusFilter, setStatus]     = useState(() => {
    if (typeof window === "undefined") return "";
    const s = new URLSearchParams(window.location.search).get("status") ?? "";
    return STATUSES.includes(s) ? s : "";
  });
  const [search, setSearch]           = useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("search") ?? "";
  });
  const [debouncedSearch, setDebounced] = useState(search);
  const [loading, setLoading]         = useState(true);
  const [showUpload, setShowUpload]   = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Batch | null>(null);
  const [recoveryTarget, setRecoveryTarget] = useState<Batch | null>(null);
  const [actionLoading, setActionLoading] = useState<Set<number>>(new Set());
  const [reconciling, setReconciling] = useState(false);
  const [reconcileResult, setReconcileResult] = useState<ReconcileResult | null>(null);
  const [reviewerWorkload, setReviewerWorkload] = useState<Record<string, number>>({});
  const modelProvider: QCModelSelection["provider"] = "ollama";
  const [textModel, setTextModel]     = useState(MODEL_OPTIONS.ollama.text[0]);
  const visionModel                   = MODEL_OPTIONS.ollama.vision[0];
  const searchMountedRef              = useRef(false);

  const setActionBusy = useCallback((id: number, on: boolean) => {
    setActionLoading(prev => {
      const n = new Set(prev);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });
  }, []);

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      if (searchMountedRef.current) setPage(0);
      else searchMountedRef.current = true;
    }, 350);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    batchLog("load:start", { page, statusFilter, debouncedSearch });
    setLoading(true);
    try {
      const [bRes, uRes, dash] = await Promise.all([
        getAdminBatches(page, statusFilter || undefined, debouncedSearch || undefined),
        getAllUsers(),
        getAdminDashboard(),
      ]);
      setBatches(bRes.content);
      setTotalPages(bRes.totalPages);
      setTotalElements(Number(bRes.totalElements ?? bRes.content.length));
      setReviewers(uRes.filter(u => u.role === "REVIEWER"));
      setReviewerWorkload((dash.reviewerWorkload as Record<string, number> | undefined) ?? {});
      batchLog("load:success", { count: bRes.content.length });
    } catch (e) {
      batchLog("load:error", e);
      toast.error("Failed to load batches");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, debouncedSearch]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  // Sync URL params
  useEffect(() => {
    const params = new URLSearchParams();
    if (statusFilter) params.set("status", statusFilter);
    if (debouncedSearch) params.set("search", debouncedSearch);
    if (page > 0) params.set("page", String(page));
    window.history.replaceState(null, "", params.toString() ? `/admin/batches?${params}` : "/admin/batches");
  }, [debouncedSearch, page, statusFilter]);

  const { progress, startPolling, stopPolling } = useBatchPolling(batches, () => {
    void load();
  });

  async function handleProcessQC(batch: Batch) {
    setActionBusy(batch.id, true);
    try {
      await processQC(batch.id, { provider: modelProvider, textModel, visionModel });
      setBatches(prev => prev.map(b => b.id === batch.id ? { ...b, status: "QC_PROCESSING", errorMessage: undefined } : b));
      toast.info(`QC started for "${batch.parentBatchId}"`, `${MODEL_OPTIONS[modelProvider].label} · ${textModel}`);
      startPolling({ ...batch, status: "QC_PROCESSING" });
      await load();
    } catch (e) {
      toast.error("QC trigger failed", String(e));
    } finally {
      setActionBusy(batch.id, false);
    }
  }

  async function handleStopQC(batch: Batch) {
    setActionBusy(batch.id, true);
    try {
      await cancelQC(batch.id);
      stopPolling(batch.id);
      removeJob(`qc-${batch.id}`);
      setBatches(prev => prev.map(b => b.id === batch.id ? { ...b, status: "UPLOADED", errorMessage: "QC stopped by admin. Click Run QC to start again." } : b));
      toast.info(`QC stopped for "${batch.parentBatchId}"`, "Run QC is available again");
      await load();
    } catch (e) {
      toast.error("Stop QC failed", String(e));
    } finally {
      setActionBusy(batch.id, false);
    }
  }

  async function handleAssign(batchId: number, reviewerId: number) {
    setActionBusy(batchId, true);
    try {
      await assignReviewer(batchId, reviewerId);
      toast.success("Reviewer assigned");
      await load();
    } catch (e) {
      toast.error("Assignment failed", String(e));
    } finally {
      setActionBusy(batchId, false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await deleteBatch(deleteTarget.id);
      toast.success(`Batch "${deleteTarget.parentBatchId}" deleted`);
      setDeleteTarget(null);
      await load();
    } catch (e) {
      toast.error("Delete failed", String(e));
    }
  }

  async function handleReconcile() {
    setReconciling(true); setReconcileResult(null);
    try {
      const r = await reconcileStuckBatches();
      setReconcileResult(r);
      if (r.stuckFound === 0) toast.info("No stuck batches found");
      else toast.success("Reconciliation complete", r.message);
      if (r.retried > 0) await load();
    } catch (e) {
      toast.error("Reconciliation failed", String(e));
    } finally {
      setReconciling(false);
    }
  }

  const pageStats = {
    total:     batches.length,
    running:   batches.filter(b => b.status === "QC_PROCESSING").length,
    review:    batches.filter(b => b.status === "REVIEW_PENDING" || b.status === "IN_REVIEW").length,
    ready:     batches.filter(b => b.status === "UPLOADED" || b.status === "ERROR").length,
    completed: batches.filter(b => b.status === "COMPLETED").length,
  };
  const activeFilterLabel = statusFilter ? statusFilter.replace(/_/g, " ") : "All statuses";

  return (
    <div className="max-w-[1500px] p-6">
      {/* Header */}
      <div className="flex flex-col gap-4 mb-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600">Document intake</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-white">Batches</h1>
          <p className="mt-1 text-sm text-slate-500">Upload, validate, process, assign, and recover appraisal document sets.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={handleReconcile} disabled={reconciling} title="Find and recover batches stuck in QC_PROCESSING"
            className="inline-flex h-9 items-center gap-1.5 rounded-md border border-white/10 bg-[#11161C] px-3 text-sm text-slate-300 transition-colors hover:border-white/15 hover:bg-white/[0.04] hover:text-white disabled:opacity-50">
            <RefreshCw size={13} className={reconciling ? "animate-spin" : ""} />
            Reconcile
          </button>
          <button onClick={() => setShowUpload(true)}
            className="inline-flex h-9 items-center gap-1.5 rounded-md border border-blue-400/30 bg-blue-600 px-4 text-sm font-semibold text-white shadow-[0_0_22px_rgba(59,130,246,0.16)] transition-colors hover:bg-blue-500">
            <Plus size={14} /> Upload batch
          </button>
        </div>
      </div>

      {/* Summary pills */}
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
        <SummaryPill icon={FileStack}    label="On page"      value={pageStats.total}     tone="slate"  />
        <SummaryPill icon={Clock3}       label="QC running"   value={pageStats.running}   tone="indigo" />
        <SummaryPill icon={UserPlus}     label="Needs review" value={pageStats.review}    tone="amber"  />
        <SummaryPill icon={Play}         label="Ready / retry"value={pageStats.ready}     tone="blue"   />
        <SummaryPill icon={CheckCircle2} label="Completed"    value={pageStats.completed} tone="green"  />
      </div>

      {/* Filters */}
      <div className="mb-4 rounded-lg border border-white/10 bg-[#11161C]/95 p-3 shadow-[0_12px_32px_rgba(0,0,0,0.16)]">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative w-full sm:max-w-sm">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Search all batches by ID or client…"
                className="h-9 w-full rounded-md border border-white/10 bg-[#0B0F14]/70 pl-8 pr-3 text-sm text-white placeholder-slate-600 transition-colors focus:border-blue-500/70 focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
            </div>
            <select value={statusFilter} onChange={e => { setStatus(e.target.value); setPage(0); }}
              className="h-9 w-full rounded-md border border-white/10 bg-[#0B0F14]/70 px-3 text-sm text-slate-300 transition-colors focus:border-blue-500/70 focus:outline-none focus:ring-2 focus:ring-blue-500/30 sm:w-48"
              aria-label="Filter by status">
              <option value="">All statuses</option>
              {STATUSES.filter(Boolean).map(s => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </select>
            {(search || statusFilter) && (
              <button onClick={() => { setSearch(""); setStatus(""); setPage(0); }}
                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-white/10 bg-[#0B0F14]/70 px-3 text-sm text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white">
                <XCircle size={13} /> Clear
              </button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-white/10 bg-[#0B0F14]/70 px-2 py-2">
            <span className="inline-flex items-center gap-1.5 px-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              <SlidersHorizontal size={12} /> QC model
            </span>
            <span className="h-8 rounded-md border border-white/10 bg-[#11161C] px-2 text-xs leading-8 text-slate-300">
              {MODEL_OPTIONS[modelProvider].label}
            </span>
            <select value={textModel} onChange={e => setTextModel(e.target.value)}
              className="h-8 min-w-[150px] rounded-md border border-white/10 bg-[#11161C] px-2 text-xs text-slate-300 focus:border-blue-500/70 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              aria-label="Select QC text model">
              {MODEL_OPTIONS[modelProvider].text.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <span className="h-8 rounded-md border border-white/10 bg-[#11161C] px-2 text-xs leading-8 text-slate-300">
              Vision {visionModel}
            </span>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
          <span>Showing {batches.length} of {totalElements} matching row{totalElements === 1 ? "" : "s"} on page {page + 1}</span>
          <span className="hidden h-1 w-1 rounded-full bg-slate-700 sm:inline-block" />
          <span>{activeFilterLabel}</span>
          {debouncedSearch && <span>Global search <span className="rounded border border-white/10 bg-[#161B22] px-1.5 py-0.5 font-mono text-slate-400">{debouncedSearch}</span></span>}
        </div>
      </div>

      {reconcileResult && <ReconcileSummary result={reconcileResult} onDismiss={() => setReconcileResult(null)} />}

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-white/10 bg-[#11161C] shadow-[0_16px_40px_rgba(0,0,0,0.2)]">
        <div className="data-scroll">
          <table className="w-full min-w-[1060px] text-sm">
            <thead>
              <tr className="border-b border-white/10 bg-[#0B0F14]/80">
                {["Batch", "Client", "Status", "Files", "Reviewer", "Date", "Actions"].map((h, i) => (
                  <th key={h} className={`sticky top-0 z-10 bg-[#0B0F14] px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500 ${i === 6 ? "text-right" : "text-left"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {loading ? (
                <tr><td colSpan={7} className="p-0"><TableSkeleton rows={6} cols={7} /></td></tr>
              ) : batches.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <EmptyState
                      icon={Search}
                      title={debouncedSearch || statusFilter ? "No batches match your filters" : "No batches yet"}
                      description={!debouncedSearch && !statusFilter ? "Upload a ZIP archive to get started." : undefined}
                      action={!debouncedSearch && !statusFilter ? (
                        <button onClick={() => setShowUpload(true)} className="flex items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300 transition-colors">
                          <Plus size={14} /> Upload first batch
                        </button>
                      ) : undefined}
                    />
                  </td>
                </tr>
              ) : batches.map(b => (
                <BatchRow
                  key={b.id}
                  batch={b}
                  isLoading={actionLoading.has(b.id)}
                  progress={progress[b.id]}
                  reviewers={reviewers}
                  reviewerWorkload={reviewerWorkload}
                  onProcessQC={handleProcessQC}
                  onStopQC={handleStopQC}
                  onAssign={handleAssign}
                  onDelete={setDeleteTarget}
                  onOpenRecovery={setRecoveryTarget}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
            className="flex h-8 items-center gap-1.5 rounded-md border border-white/10 px-3 text-sm text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white disabled:opacity-30">
            <ChevronLeft size={14} /> Previous
          </button>
          <span className="text-xs text-slate-500">Page {page + 1} of {totalPages}</span>
          <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
            className="flex h-8 items-center gap-1.5 rounded-md border border-white/10 px-3 text-sm text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white disabled:opacity-30">
            Next <ChevronRight size={14} />
          </button>
        </div>
      )}

      {/* Modals */}
      <UploadModal open={showUpload} onClose={() => setShowUpload(false)}
        onUploaded={(_batchId, ref, fileCount) => {
          toast.success(`Batch "${ref}" uploaded`, `${fileCount} files ready for QC`);
          void load();
        }} />
      <ConfirmDialog open={!!deleteTarget} title="Delete batch"
        message={`Delete "${deleteTarget?.parentBatchId}"? All associated files and QC results will be permanently removed. This cannot be undone.`}
        confirmLabel="Delete batch" danger confirmationText={deleteTarget?.parentBatchId}
        onConfirm={handleDelete} onCancel={() => setDeleteTarget(null)} />
      <BatchRecoveryDrawer
        batch={recoveryTarget}
        busy={recoveryTarget ? actionLoading.has(recoveryTarget.id) : false}
        onClose={() => setRecoveryTarget(null)}
        onRetry={batch => void handleProcessQC(batch)}
        onDelete={batch => { setRecoveryTarget(null); setDeleteTarget(batch); }}
        onReupload={() => { setRecoveryTarget(null); setShowUpload(true); }}
      />
    </div>
  );
}

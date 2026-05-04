"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  Search, Plus, RefreshCw, ChevronLeft, ChevronRight, AlertCircle, Square,
  Play, Trash2, UserPlus, SlidersHorizontal, XCircle, FileStack, Clock3,
  CheckCircle2, AlertTriangle, Upload,
} from "lucide-react";
import type { ComponentType } from "react";
import {
  getAdminBatches, getUsers, processQC, assignReviewer, deleteBatch,
  getBatchStatus, getBatchQCProgress, reconcileStuckBatches, cancelQC,
  getAdminDashboard, type Batch, type User, type QCModelSelection,
} from "@/lib/api";
import StatusBadge from "@/components/shared/StatusBadge";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import UploadModal from "@/components/admin/UploadModal";
import { TableSkeleton } from "@/components/shared/Skeleton";
import EmptyState from "@/components/shared/EmptyState";
import { toast } from "@/lib/toast";
import { trackJob, updateJob, removeJob } from "@/lib/jobs";

const STATUSES = ["", "UPLOADED", "VALIDATING", "VALIDATION_FAILED", "QC_PROCESSING", "REVIEW_PENDING", "IN_REVIEW", "COMPLETED", "ERROR"];

function batchLog(event: string, payload?: unknown) {
  if (process.env.NODE_ENV !== "production") {
    console.log(`[BatchesPage] ${event}`, payload ?? "");
  }
}

// Per-batch QC progress tracker
interface BatchProgress {
  current: number;
  total: number;
  message: string;
  stage: string;
  percent: number;
  modelProvider?: string;
  modelName?: string;
  visionModel?: string;
}

type ReconcileResult = {
  stuckFound: number;
  retried: number;
  abandoned: number;
  pythonHealthy: boolean;
  message: string;
};

const MODEL_OPTIONS: Record<QCModelSelection["provider"], { label: string; text: string[]; vision: string[] }> = {
  ollama: {
    label: "Ollama",
    text: ["llava:7b", "llava:13b"],
    vision: ["llava:7b", "llava:13b"],
  },
};

export default function BatchesPage() {
  const [batches, setBatches]     = useState<Batch[]>([]);
  const [reviewers, setReviewers] = useState<User[]>([]);
  const [page, setPage]           = useState(() => {
    if (typeof window === "undefined") return 0;
    const parsed = Number(new URLSearchParams(window.location.search).get("page") ?? 0);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : 0;
  });
  const [totalPages, setTotalPages] = useState(1);
  const [totalElements, setTotalElements] = useState(0);
  const [statusFilter, setStatus] = useState(() => {
    if (typeof window === "undefined") return "";
    const status = new URLSearchParams(window.location.search).get("status") ?? "";
    return STATUSES.includes(status) ? status : "";
  });
  const [search, setSearch]       = useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("search") ?? "";
  });
  const [debouncedSearch, setDebounced] = useState(search);
  const [loading, setLoading]     = useState(true);
  const [showUpload, setShowUpload]     = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Batch | null>(null);
  const [recoveryTarget, setRecoveryTarget] = useState<Batch | null>(null);
  const [actionLoading, setActionLoading] = useState<Set<number>>(new Set());
  const [reconciling, setReconciling]     = useState(false);
  const [reconcileResult, setReconcileResult] = useState<ReconcileResult | null>(null);
  const [progress, setProgress]           = useState<Record<number, BatchProgress>>({});
  const [reviewerWorkload, setReviewerWorkload] = useState<Record<string, number>>({});
  const modelProvider: QCModelSelection["provider"] = "ollama";
  const [textModel, setTextModel]         = useState(MODEL_OPTIONS.ollama.text[0]);
  const visionModel = MODEL_OPTIONS.ollama.vision[0];
  const pollingRef = useRef<Record<number, ReturnType<typeof setInterval>>>({});
  const searchMountedRef = useRef(false);

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      if (searchMountedRef.current) {
        setPage(0);
      } else {
        searchMountedRef.current = true;
      }
    }, 350);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    batchLog("load:start", { page, statusFilter, debouncedSearch });
    setLoading(true);
    try {
      const [bRes, uRes, dash] = await Promise.all([
        getAdminBatches(page, statusFilter || undefined, debouncedSearch || undefined),
        getUsers(0, 200),
        getAdminDashboard(),
      ]);
      batchLog("load:success", {
        page: bRes.number,
        totalPages: bRes.totalPages,
        search: debouncedSearch,
        batches: bRes.content.map(b => ({
          id: b.id,
          parentBatchId: b.parentBatchId,
          client: b.client?.name,
          status: b.status,
          fileCount: b.fileCount,
          updatedAt: b.updatedAt,
        })),
        reviewers: uRes.content.filter(u => u.role === "REVIEWER").length,
      });
      setBatches(bRes.content);
      setTotalPages(bRes.totalPages);
      setTotalElements(Number(bRes.totalElements ?? bRes.content.length));
      setReviewers(uRes.content.filter(u => u.role === "REVIEWER"));
      setReviewerWorkload((dash.reviewerWorkload as Record<string, number> | undefined) ?? {});
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

  useEffect(() => {
    batchLog("filters:change", { search, debouncedSearch, statusFilter, page });
  }, [search, debouncedSearch, statusFilter, page]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (statusFilter) params.set("status", statusFilter);
    if (debouncedSearch) params.set("search", debouncedSearch);
    if (page > 0) params.set("page", String(page));
    const nextUrl = params.toString() ? `/admin/batches?${params}` : "/admin/batches";
    window.history.replaceState(null, "", nextUrl);
  }, [debouncedSearch, page, statusFilter]);

  useEffect(() => {
    batchLog("progress:change", progress);
  }, [progress]);

  // Auto-start polling for any batch already in QC_PROCESSING when the list loads.
  // This handles page refresh, navigation back, or batches triggered in a prior session.
  useEffect(() => {
    batches.forEach(b => {
      if (b.status === "QC_PROCESSING" && !pollingRef.current[b.id]) {
        batchLog("poll:auto-start", { batchId: b.id, parentBatchId: b.parentBatchId });
        startPolling(b);
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batches]);

  // Start polling a batch that just entered QC_PROCESSING
  function startPolling(batch: Batch) {
    const batchId = batch.id;
    const jobKey = `qc-${batchId}`;
    batchLog("poll:start", { batchId, parentBatchId: batch.parentBatchId });
    // Use the real processing unit: appraisal files. Contracts and engagement
    // letters support QC, but each saved QCResult corresponds to one appraisal.
    const appraisalFiles = batch.files?.filter(f => f.fileType === "APPRAISAL") ?? [];
    const initialTotal = appraisalFiles.length > 0 ? appraisalFiles.length : 1;
    const batchFileCount = batch.fileCount ?? batch.files?.length ?? 0;

    trackJob({
      id: jobKey,
      label: `QC: ${batch.parentBatchId}`,
      current: 0,
      total: initialTotal,
      batchId,
      startedAt: Date.now(),
      message: "Starting QC processing",
      unitLabel: "appraisal set",
      detail: `${batchFileCount} uploaded file${batchFileCount === 1 ? "" : "s"} in this batch`,
    });

    if (pollingRef.current[batchId]) return; // already polling

    const poll = async () => {
      try {
        const [statusRes, progressRes] = await Promise.all([
          getBatchStatus(batchId),
          getBatchQCProgress(batchId),
        ]);
        batchLog("poll:tick", { batchId, status: statusRes, progress: progressRes });
        const total = Math.max(progressRes.total || statusRes.processingTotalFiles || appraisalFiles.length || 1, 1);
        const done = Math.min(Math.max(progressRes.current, statusRes.completedFiles ?? 0), total);
        const modelLabel = progressRes.modelName
          ? `${progressRes.modelProvider ?? "model"}: ${progressRes.modelName}`
          : undefined;
        updateJob(jobKey, done, total, {
          message: progressRes.message || "QC processing is running",
          stage: progressRes.stage || "processing",
          modelLabel,
          unitLabel: total === 1 ? "appraisal set" : "appraisal sets",
          detail: `${statusRes.totalFiles ?? batchFileCount} uploaded file${(statusRes.totalFiles ?? batchFileCount) === 1 ? "" : "s"} in this batch`,
        });
        setProgress(p => ({
          ...p,
          [batchId]: {
            current: done,
            total,
            message: progressRes.message || "QC processing is running",
            stage: progressRes.stage || "processing",
            percent: progressRes.percent ?? Math.round((done / total) * 100),
            modelProvider: progressRes.modelProvider,
            modelName: progressRes.modelName,
            visionModel: progressRes.visionModel,
          },
        }));

        if (statusRes.status !== "QC_PROCESSING") {
          if (pollingRef.current[batchId]) clearInterval(pollingRef.current[batchId]);
          delete pollingRef.current[batchId];
          removeJob(jobKey);
          setProgress(p => { const n = {...p}; delete n[batchId]; return n; });

          if (statusRes.status === "COMPLETED" || statusRes.status === "REVIEW_PENDING") {
            toast.success(`Batch "${batch.parentBatchId}" QC complete`, `${done} file${done !== 1 ? "s" : ""} processed`);
          } else if (statusRes.status === "ERROR") {
            toast.error(`Batch "${batch.parentBatchId}" failed`, "Check the error details in the batch list");
          } else if (statusRes.status === "UPLOADED") {
            toast.info(`Batch "${batch.parentBatchId}" QC stopped`, "Run QC is available again");
          }
          await load();
        }
      } catch (e) {
        batchLog("poll:error", { batchId, error: e });
      }
    };

    void poll();
    const interval = setInterval(poll, 5000);

    pollingRef.current[batchId] = interval;
  }

  // Cleanup polling on unmount
  useEffect(() => {
    const polling = pollingRef.current;
    return () => { Object.values(polling).forEach(clearInterval); };
  }, []);

  function setLoading1(id: number, on: boolean) {
    setActionLoading(prev => {
      const n = new Set(prev);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });
  }

  async function handleProcessQC(batch: Batch) {
    batchLog("qc:start-click", { batchId: batch.id, parentBatchId: batch.parentBatchId, modelProvider, textModel, visionModel });
    setLoading1(batch.id, true);
    try {
      const response = await processQC(batch.id, { provider: modelProvider, textModel, visionModel });
      batchLog("qc:start-response", response);
      setBatches(prev => prev.map(b => b.id === batch.id ? { ...b, status: "QC_PROCESSING", errorMessage: undefined } : b));
      toast.info(`QC started for "${batch.parentBatchId}"`, `${MODEL_OPTIONS[modelProvider].label} · ${textModel}`);
      // Find the updated batch and start polling
      const updated = { ...batch, status: "QC_PROCESSING" };
      startPolling(updated);
      await load();
    } catch (e) {
      batchLog("qc:start-error", e);
      toast.error("QC trigger failed", String(e));
    } finally {
      setLoading1(batch.id, false);
    }
  }

  async function handleStopQC(batch: Batch) {
    batchLog("qc:stop-click", { batchId: batch.id, parentBatchId: batch.parentBatchId });
    setLoading1(batch.id, true);
    try {
      const response = await cancelQC(batch.id);
      batchLog("qc:stop-response", response);
      if (pollingRef.current[batch.id]) {
        clearInterval(pollingRef.current[batch.id]);
        delete pollingRef.current[batch.id];
      }
      removeJob(`qc-${batch.id}`);
      setProgress(p => { const n = {...p}; delete n[batch.id]; return n; });
      setBatches(prev => prev.map(b => b.id === batch.id ? { ...b, status: "UPLOADED", errorMessage: "QC stopped by admin. Click Run QC to start again." } : b));
      toast.info(`QC stopped for "${batch.parentBatchId}"`, "Run QC is available again");
      await load();
    } catch (e) {
      batchLog("qc:stop-error", e);
      toast.error("Stop QC failed", String(e));
    } finally {
      setLoading1(batch.id, false);
    }
  }

  async function handleAssign(batchId: number, reviewerId: number) {
    batchLog("assign:start", { batchId, reviewerId });
    setLoading1(batchId, true);
    try {
      await assignReviewer(batchId, reviewerId);
      batchLog("assign:success", { batchId, reviewerId });
      toast.success("Reviewer assigned");
      await load();
    } catch (e) {
      batchLog("assign:error", e);
      toast.error("Assignment failed", String(e));
    } finally {
      setLoading1(batchId, false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    batchLog("delete:start", { batchId: deleteTarget.id, parentBatchId: deleteTarget.parentBatchId });
    try {
      await deleteBatch(deleteTarget.id);
      batchLog("delete:success", { batchId: deleteTarget.id });
      toast.success(`Batch "${deleteTarget.parentBatchId}" deleted`);
      setDeleteTarget(null);
      await load();
    } catch (e) {
      batchLog("delete:error", e);
      toast.error("Delete failed", String(e));
    }
  }

  async function handleReconcile() {
    batchLog("reconcile:start");
    setReconciling(true);
    setReconcileResult(null);
    try {
      const r = await reconcileStuckBatches();
      batchLog("reconcile:response", r);
      setReconcileResult(r);
      if (r.stuckFound === 0) toast.info("No stuck batches found");
      else toast.success("Reconciliation complete", r.message);
      if (r.retried > 0) await load();
    } catch (e) {
      batchLog("reconcile:error", e);
      toast.error("Reconciliation failed", String(e));
    } finally {
      setReconciling(false);
    }
  }

  const filtered = batches;
  const pageStats = {
    total: batches.length,
    running: batches.filter(b => b.status === "QC_PROCESSING").length,
    review: batches.filter(b => b.status === "REVIEW_PENDING" || b.status === "IN_REVIEW").length,
    ready: batches.filter(b => b.status === "UPLOADED" || b.status === "ERROR").length,
    completed: batches.filter(b => b.status === "COMPLETED").length,
  };
  const activeFilterLabel = statusFilter ? statusFilter.replace(/_/g, " ") : "All statuses";

  return (
    <div className="p-6 max-w-[1500px]">
      {/* Header */}
      <div className="flex flex-col gap-4 mb-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Batches</h1>
          <p className="text-slate-500 text-sm mt-0.5">Upload and manage appraisal document sets</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleReconcile} disabled={reconciling}
            title="Find and recover batches stuck in QC_PROCESSING"
            className="h-9 px-3 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-slate-300 text-sm inline-flex items-center gap-1.5 transition-colors"
          >
            <RefreshCw size={13} className={reconciling ? "animate-spin" : ""} />
            Reconcile
          </button>
          <button
            onClick={() => setShowUpload(true)}
            className="h-9 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm inline-flex items-center gap-1.5 font-medium transition-colors"
          >
            <Plus size={14} /> Upload batch
          </button>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
        <SummaryPill icon={FileStack} label="On page" value={pageStats.total} tone="slate" />
        <SummaryPill icon={Clock3} label="QC running" value={pageStats.running} tone="indigo" />
        <SummaryPill icon={UserPlus} label="Needs review" value={pageStats.review} tone="amber" />
        <SummaryPill icon={Play} label="Ready / retry" value={pageStats.ready} tone="blue" />
        <SummaryPill icon={CheckCircle2} label="Completed" value={pageStats.completed} tone="green" />
      </div>

      {/* Filters row */}
      <div className="mb-4 rounded-lg border border-slate-800 bg-slate-900/80 p-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative w-full sm:max-w-sm">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search all batches by ID or client…"
            className="w-full h-9 bg-slate-900 border border-slate-700 rounded-lg pl-8 pr-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-colors"
          />
            </div>
            <select
              value={statusFilter} onChange={e => { setStatus(e.target.value); setPage(0); }}
              className="h-9 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 text-sm text-slate-300 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-500 sm:w-48"
              aria-label="Filter by status"
            >
              <option value="">All statuses</option>
              {STATUSES.filter(Boolean).map(s => (
                <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
              ))}
            </select>
            {(search || statusFilter) && (
              <button
                onClick={() => { setSearch(""); setStatus(""); setPage(0); }}
                className="h-9 px-3 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 text-slate-400 text-sm inline-flex items-center justify-center gap-1.5 transition-colors"
              >
                <XCircle size={13} /> Clear
              </button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/70 px-2 py-2">
            <span className="inline-flex items-center gap-1.5 px-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              <SlidersHorizontal size={12} /> QC model
            </span>
            <span className="h-8 rounded-md border border-slate-700 bg-slate-900 px-2 text-xs leading-8 text-slate-300">
              {MODEL_OPTIONS[modelProvider].label}
            </span>
            <select
              value={textModel}
              onChange={e => setTextModel(e.target.value)}
              className="h-8 min-w-[150px] rounded-md border border-slate-700 bg-slate-900 px-2 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
              aria-label="Select QC text model"
            >
              {MODEL_OPTIONS[modelProvider].text.map(model => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>
            <span className="h-8 rounded-md border border-slate-700 bg-slate-900 px-2 text-xs leading-8 text-slate-300">
              Vision {visionModel}
            </span>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
          <span>Showing {filtered.length} of {totalElements} matching row{totalElements === 1 ? "" : "s"} on page {page + 1}</span>
          <span className="hidden h-1 w-1 rounded-full bg-slate-700 sm:inline-block" />
          <span>{activeFilterLabel}</span>
          {debouncedSearch && <span>Global search <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-slate-400">{debouncedSearch}</span></span>}
        </div>
      </div>

      {reconcileResult && (
        <ReconcileSummary result={reconcileResult} onDismiss={() => setReconcileResult(null)} />
      )}

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900">
        <div className="data-scroll">
        <table className="w-full min-w-[1060px] text-sm">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-950/40">
              <th className="sticky top-0 z-10 bg-slate-950 px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Batch</th>
              <th className="sticky top-0 z-10 bg-slate-950 px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Client</th>
              <th className="sticky top-0 z-10 bg-slate-950 px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Status</th>
              <th className="sticky top-0 z-10 bg-slate-950 px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Files</th>
              <th className="sticky top-0 z-10 bg-slate-950 px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Reviewer</th>
              <th className="sticky top-0 z-10 bg-slate-950 px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Date</th>
              <th className="sticky top-0 z-10 bg-slate-950 px-4 py-3 text-right text-[11px] font-semibold uppercase tracking-wider text-slate-500">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {loading ? (
              <tr><td colSpan={7} className="p-0"><TableSkeleton rows={6} cols={7} /></td></tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <EmptyState
                    icon={Search}
                    title={debouncedSearch || statusFilter ? "No batches match your filters" : "No batches yet"}
                    description={!debouncedSearch && !statusFilter ? "Upload a ZIP archive to get started." : undefined}
                    action={!debouncedSearch && !statusFilter ? (
                      <button onClick={() => setShowUpload(true)}
                        className="flex items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300 transition-colors">
                        <Plus size={14} /> Upload first batch
                      </button>
                    ) : undefined}
                  />
                </td>
              </tr>
            ) : filtered.map(b => {
              const isLoading = actionLoading.has(b.id);
              const prog = progress[b.id];
              const pct = prog ? prog.percent : 0;

              return (
                <tr key={b.id} className={`transition-colors ${b.status === "QC_PROCESSING" ? "bg-indigo-950/10" : "hover:bg-slate-800/30"}`}>
                  {/* Batch ID */}
                  <td className="px-4 py-3">
                    <div className="font-mono text-xs text-slate-200 max-w-[190px] truncate" title={b.parentBatchId}>
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
                    {b.status === "QC_PROCESSING" && prog && (
                      <div className="mt-1.5">
                        <div className="flex justify-between text-[10px] text-slate-500 mb-0.5">
                          <span className="max-w-[150px] truncate" title={prog.message}>{prog.message}</span>
                          <span className="font-mono">{pct}%</span>
                        </div>
                        <div className="w-32 h-1 bg-slate-800 rounded-full overflow-hidden">
                          <div className="h-full bg-indigo-500 rounded-full transition-all duration-500" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
                        </div>
                        <div className="mt-0.5 text-[10px] text-slate-600">
                          {prog.current}/{prog.total} appraisal set{prog.total === 1 ? "" : "s"} · {b.fileCount ?? b.files?.length ?? 0} files · {prog.stage.replace(/_/g, " ")}
                        </div>
                        {prog.modelName && (
                          <div className="mt-0.5 text-[10px] text-blue-400 max-w-[150px] truncate">
                            {prog.modelProvider ?? "model"} · {prog.modelName}
                          </div>
                        )}
                      </div>
                    )}
                    {b.errorMessage && (b.status === "ERROR" || b.status === "VALIDATION_FAILED") && (
                      <button
                        type="button"
                        onClick={() => setRecoveryTarget(b)}
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
                  {/* Files — prefer formula-computed count, fall back to loaded array length */}
                  <td className="px-4 py-3 text-xs text-slate-400 tabular-nums">
                    {b.fileCount ?? b.files?.length ?? 0}
                  </td>
                  {/* Reviewer */}
                  <td className="px-4 py-3 text-xs">
                    {b.assignedReviewer
                      ? <span className="text-slate-300">{b.assignedReviewer.fullName ?? b.assignedReviewer.username}</span>
                      : <span className="text-slate-600">Unassigned</span>}
                  </td>
                  {/* Date */}
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {new Date(b.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                  </td>
                  {/* Actions */}
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      {/* Run QC */}
                      {(b.status === "UPLOADED" || b.status === "VALIDATING" || b.status === "ERROR") && (
                        <button
                          onClick={() => handleProcessQC(b)}
                          disabled={isLoading}
                          className="h-8 min-w-[88px] px-2.5 rounded-md bg-indigo-900/50 hover:bg-indigo-800/60 border border-indigo-800/50 text-indigo-200 text-xs font-medium transition-colors disabled:opacity-40 inline-flex items-center justify-center gap-1.5"
                        >
                          {isLoading ? (
                            <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                            </svg>
                          ) : <Play size={12} />}
                          {b.status === "ERROR" ? "Retry" : "Run QC"}
                        </button>
                      )}

                      {/* Processing state */}
                      {b.status === "QC_PROCESSING" && !prog && (
                        <span className="text-[11px] text-indigo-400 flex items-center gap-1">
                          <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                          </svg>
                          Processing
                        </span>
                      )}

                      {b.status === "QC_PROCESSING" && (
                        <button
                          onClick={() => handleStopQC(b)}
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
                      {b.status === "REVIEW_PENDING" && (
                        reviewers.length > 0 ? (
                          <ReviewerAssignControl
                            batch={b}
                            reviewers={reviewers}
                            workload={reviewerWorkload}
                            disabled={isLoading}
                            onAssign={reviewerId => handleAssign(b.id, reviewerId)}
                          />
                        ) : (
                          <span className="h-7 px-2 rounded-md border border-amber-900/60 text-[11px] text-amber-300 flex items-center">
                            No reviewers
                          </span>
                        )
                      )}

                      {/* Delete */}
                      <button
                        onClick={() => setDeleteTarget(b)}
                        disabled={b.status === "QC_PROCESSING"}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-red-950/40 hover:text-red-300 disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-slate-600"
                        title={b.status === "QC_PROCESSING" ? "Stop QC before deleting this batch" : "Delete batch"}
                        aria-label={b.status === "QC_PROCESSING" ? "Stop QC before deleting this batch" : "Delete batch"}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
            className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-slate-700 text-slate-400 disabled:opacity-30 hover:text-white hover:bg-slate-800 text-sm transition-colors"
          >
            <ChevronLeft size={14} /> Previous
          </button>
          <span className="text-xs text-slate-500">Page {page + 1} of {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
            className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-slate-700 text-slate-400 disabled:opacity-30 hover:text-white hover:bg-slate-800 text-sm transition-colors"
          >
            Next <ChevronRight size={14} />
          </button>
        </div>
      )}

      {/* Modals */}
      <UploadModal
        open={showUpload}
        onClose={() => setShowUpload(false)}
        onUploaded={(_batchId, ref, fileCount) => {
          toast.success(`Batch "${ref}" uploaded`, `${fileCount} files ready for QC`);
          load();
        }}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete batch"
        message={`Delete "${deleteTarget?.parentBatchId}"? All associated files and QC results will be permanently removed. This cannot be undone.`}
        confirmLabel="Delete batch"
        danger
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
      <BatchRecoveryDrawer
        batch={recoveryTarget}
        busy={recoveryTarget ? actionLoading.has(recoveryTarget.id) : false}
        onClose={() => setRecoveryTarget(null)}
        onRetry={(batch) => handleProcessQC(batch)}
        onDelete={(batch) => { setRecoveryTarget(null); setDeleteTarget(batch); }}
        onReupload={() => { setRecoveryTarget(null); setShowUpload(true); }}
      />
    </div>
  );
}

function SummaryPill({ icon: Icon, label, value, tone }: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: number;
  tone: "slate" | "blue" | "indigo" | "amber" | "green";
}) {
  const tones = {
    slate: "border-slate-800 bg-slate-900 text-slate-300",
    blue: "border-blue-900/50 bg-blue-950/30 text-blue-200",
    indigo: "border-indigo-900/50 bg-indigo-950/30 text-indigo-200",
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

function ReconcileSummary({ result, onDismiss }: { result: ReconcileResult; onDismiss: () => void }) {
  const changed = result.retried + result.abandoned;
  return (
    <div className="mb-4 rounded-lg border border-slate-800 bg-slate-900 p-4">
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border ${
          changed > 0 ? "border-amber-800/50 bg-amber-950/40 text-amber-300" : "border-green-800/50 bg-green-950/30 text-green-300"
        }`}>
          <RefreshCw size={14} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-slate-200">Reconciliation result</div>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">{result.message}</p>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <RecoveryMetric label="Stuck found" value={result.stuckFound} tone={result.stuckFound > 0 ? "amber" : "slate"} />
            <RecoveryMetric label="Retried" value={result.retried} tone={result.retried > 0 ? "blue" : "slate"} />
            <RecoveryMetric label="Abandoned" value={result.abandoned} tone={result.abandoned > 0 ? "red" : "slate"} />
            <RecoveryMetric label="QC service" value={result.pythonHealthy ? "Healthy" : "Needs check"} tone={result.pythonHealthy ? "green" : "red"} />
          </div>
        </div>
        <button
          onClick={onDismiss}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-800 hover:text-slate-300"
          aria-label="Dismiss reconciliation result"
        >
          <XCircle size={14} />
        </button>
      </div>
    </div>
  );
}

function RecoveryMetric({ label, value, tone }: { label: string; value: number | string; tone: "slate" | "amber" | "blue" | "green" | "red" }) {
  const tones = {
    slate: "border-slate-800 bg-slate-950/60 text-slate-300",
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

function ReviewerAssignControl({ batch, reviewers, workload, disabled, onAssign }: {
  batch: Batch;
  reviewers: User[];
  workload: Record<string, number>;
  disabled: boolean;
  onAssign: (reviewerId: number) => void;
}) {
  const ranked = reviewers
    .map(reviewer => {
      const active = Number(workload[String(reviewer.id)] ?? workload[reviewer.id] ?? 0);
      const sameClient = Boolean(reviewer.client?.id && batch.client?.id && reviewer.client.id === batch.client.id);
      return { reviewer, active, sameClient };
    })
    .sort((a, b) => Number(b.sameClient) - Number(a.sameClient) || a.active - b.active || displayUser(a.reviewer).localeCompare(displayUser(b.reviewer)));
  const recommended = ranked[0];
  const age = formatAge(batch.updatedAt ?? batch.createdAt);

  return (
    <div className="min-w-[210px] rounded-md border border-slate-800 bg-slate-950/60 p-2">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wide text-slate-500">Assign reviewer</span>
        <span className="text-[10px] text-amber-300">{age}</span>
      </div>
      <select
        defaultValue=""
        onChange={e => e.target.value && onAssign(Number(e.target.value))}
        disabled={disabled}
        className="h-8 w-full rounded-md border border-slate-700 bg-slate-800 px-2 text-xs text-slate-300 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-40"
        aria-label={`Assign reviewer for ${batch.parentBatchId}`}
      >
        <option value="">Assign…</option>
        {ranked.map(({ reviewer, active, sameClient }) => (
          <option key={reviewer.id} value={reviewer.id}>
            {displayUser(reviewer)} · {active} active{sameClient ? " · client fit" : ""}
          </option>
        ))}
      </select>
      {recommended && (
        <div className="mt-1.5 flex items-center justify-between gap-2 text-[10px]">
          <span className="truncate text-blue-300">Recommended: {displayUser(recommended.reviewer)}</span>
          <span className="shrink-0 text-slate-500">{recommended.active} active</span>
        </div>
      )}
    </div>
  );
}

function BatchRecoveryDrawer({ batch, busy, onClose, onRetry, onDelete, onReupload }: {
  batch: Batch | null;
  busy: boolean;
  onClose: () => void;
  onRetry: (batch: Batch) => void;
  onDelete: (batch: Batch) => void;
  onReupload: () => void;
}) {
  const drawerRef = useRef<HTMLElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!batch) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
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
        className="relative flex h-full w-full max-w-lg flex-col border-l border-slate-800 bg-slate-950 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="batch-recovery-title"
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-start gap-3 border-b border-slate-800 p-5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-red-900/60 bg-red-950/40 text-red-300">
            <AlertTriangle size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="batch-recovery-title" className="text-sm font-semibold text-white">Batch recovery</h2>
            <div className="mt-1 truncate font-mono text-xs text-slate-400" title={batch.parentBatchId}>{batch.parentBatchId}</div>
          </div>
          <button onClick={onClose} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-900 hover:text-slate-300" aria-label="Close recovery drawer">
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

          <section className="mt-5 rounded-lg border border-red-900/40 bg-red-950/20 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-red-200">Full error</h3>
            <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-red-100/85">
              {batch.errorMessage || "The backend did not provide a detailed error message for this batch."}
            </p>
          </section>

          <section className="mt-4 rounded-lg border border-slate-800 bg-slate-900/70 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Suggested recovery</h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-300">{advice.fix}</p>
            <div className="mt-3 text-xs leading-relaxed text-slate-500">{advice.reupload}</div>
          </section>
        </div>

        <div className="border-t border-slate-800 p-4">
          <div className="flex flex-wrap justify-end gap-2">
            <button
              onClick={() => onRetry(batch)}
              disabled={busy || batch.status === "VALIDATION_FAILED"}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-indigo-600 px-3 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-40"
            >
              <Play size={14} /> Retry QC
            </button>
            <button
              onClick={onReupload}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 text-sm text-slate-300 transition-colors hover:bg-slate-800"
            >
              <Upload size={14} /> Upload replacement
            </button>
            <button
              onClick={() => onDelete(batch)}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-red-900/60 bg-red-950/30 px-3 text-sm text-red-200 transition-colors hover:bg-red-950/60"
            >
              <Trash2 size={14} /> Delete batch
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}

function recoveryAdvice(batch: Batch) {
  const message = (batch.errorMessage ?? "").toLowerCase();
  if (batch.status === "VALIDATION_FAILED" || message.includes("zip") || message.includes("folder") || message.includes("validation")) {
    return {
      stage: "Upload validation",
      fix: "Check the ZIP structure and file naming, then upload a corrected archive. QC cannot run until validation passes.",
      reupload: "Use Upload replacement after deleting this failed batch if the archive contents need to change.",
    };
  }
  if (message.includes("timeout") || message.includes("timed out")) {
    return {
      stage: "QC processing",
      fix: "Retry QC once. If it fails again, reconcile stuck batches and check whether the OCR/QC service is healthy.",
      reupload: "Re-upload only if the same document repeatedly times out or appears corrupted.",
    };
  }
  if (message.includes("ocr") || message.includes("python") || message.includes("model")) {
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

function displayUser(user: User) {
  return user.fullName || user.username;
}

function formatAge(value?: string) {
  if (!value) return "Age unknown";
  const ms = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "Just updated";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${Math.max(minutes, 1)}m waiting`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h waiting`;
  return `${Math.floor(hours / 24)}d waiting`;
}

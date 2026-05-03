"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { Search, Plus, RefreshCw, ChevronLeft, ChevronRight, AlertCircle, Square } from "lucide-react";
import {
  getAdminBatches, getUsers, processQC, assignReviewer, deleteBatch,
  getBatchStatus, getBatchQCProgress, reconcileStuckBatches, cancelQC,
  type Batch, type User, type QCModelSelection,
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
  console.log(`[BatchesPage] ${event}`, payload ?? "");
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

const MODEL_OPTIONS: Record<QCModelSelection["provider"], { label: string; text: string[]; vision: string[] }> = {
  ollama: {
    label: "Ollama",
    text: ["llama3.1:8b"],
    vision: ["llava:7b"],
  },
};

export default function BatchesPage() {
  const [batches, setBatches]     = useState<Batch[]>([]);
  const [reviewers, setReviewers] = useState<User[]>([]);
  const [page, setPage]           = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [statusFilter, setStatus] = useState("");
  const [search, setSearch]       = useState("");
  const [debouncedSearch, setDebounced] = useState("");
  const [loading, setLoading]     = useState(true);
  const [showUpload, setShowUpload]     = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Batch | null>(null);
  const [actionLoading, setActionLoading] = useState<Set<number>>(new Set());
  const [reconciling, setReconciling]     = useState(false);
  const [progress, setProgress]           = useState<Record<number, BatchProgress>>({});
  const [modelProvider, setModelProvider] = useState<QCModelSelection["provider"]>("ollama");
  const [textModel, setTextModel]         = useState(MODEL_OPTIONS.ollama.text[0]);
  const [visionModel, setVisionModel]     = useState(MODEL_OPTIONS.ollama.vision[0]);
  const pollingRef = useRef<Record<number, ReturnType<typeof setInterval>>>({});

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    batchLog("load:start", { page, statusFilter });
    setLoading(true);
    try {
      const [bRes, uRes] = await Promise.all([
        getAdminBatches(page, statusFilter || undefined),
        getUsers(0),
      ]);
      batchLog("load:success", {
        page: bRes.number,
        totalPages: bRes.totalPages,
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
      setReviewers(uRes.content.filter(u => u.role === "REVIEWER"));
    } catch (e) {
      batchLog("load:error", e);
      toast.error("Failed to load batches");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    const options = MODEL_OPTIONS[modelProvider];
    batchLog("model-provider:change", { modelProvider, nextTextModel: options.text[0], nextVisionModel: options.vision[0] });
    setTextModel(options.text[0]);
    setVisionModel(options.vision[0]);
  }, [modelProvider]);

  useEffect(() => {
    batchLog("filters:change", { search, debouncedSearch, statusFilter, page });
  }, [search, debouncedSearch, statusFilter, page]);

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
    try {
      const r = await reconcileStuckBatches();
      batchLog("reconcile:response", r);
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

  // Client-side filter by search (batch ID / client name)
  const filtered = debouncedSearch
    ? batches.filter(b =>
        b.parentBatchId.toLowerCase().includes(debouncedSearch.toLowerCase()) ||
        b.client?.name?.toLowerCase().includes(debouncedSearch.toLowerCase())
      )
    : batches;

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-lg font-semibold text-white">Batches</h1>
          <p className="text-slate-500 text-sm mt-0.5">Upload and manage appraisal document sets</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReconcile} disabled={reconciling}
            title="Find and recover batches stuck in QC_PROCESSING"
            className="h-9 px-3 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-slate-300 text-sm flex items-center gap-1.5 transition-colors"
          >
            <RefreshCw size={13} className={reconciling ? "animate-spin" : ""} />
            Reconcile
          </button>
          <button
            onClick={() => setShowUpload(true)}
            className="h-9 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm flex items-center gap-1.5 font-medium transition-colors"
          >
            <Plus size={14} /> Upload batch
          </button>
        </div>
      </div>

      {/* Filters row */}
      <div className="flex items-center gap-2 mb-4">
        <div className="relative flex-1 max-w-xs">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search by batch ID or client…"
            className="w-full h-9 bg-slate-900 border border-slate-700 rounded-lg pl-8 pr-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-colors"
          />
        </div>
        <select
          value={statusFilter} onChange={e => { setStatus(e.target.value); setPage(0); }}
          className="h-9 bg-slate-900 border border-slate-700 rounded-lg px-3 text-sm text-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
        >
          <option value="">All statuses</option>
          {STATUSES.filter(Boolean).map(s => (
            <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
          ))}
        </select>
        {(search || statusFilter) && (
          <button
            onClick={() => { setSearch(""); setStatus(""); setPage(0); }}
            className="h-9 px-3 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 text-slate-400 text-sm transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">QC model</span>
        <span className="h-8 rounded-md border border-slate-700 bg-slate-950 px-2 text-xs leading-8 text-slate-300">
          Ollama
        </span>
        <select
          value={textModel}
          onChange={e => setTextModel(e.target.value)}
          className="h-8 min-w-[190px] rounded-md border border-slate-700 bg-slate-950 px-2 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          {MODEL_OPTIONS[modelProvider].text.map(model => (
            <option key={model} value={model}>{model}</option>
          ))}
        </select>
        <span className="h-8 rounded-md border border-slate-700 bg-slate-950 px-2 text-xs leading-8 text-slate-300">
          Vision: {visionModel}
        </span>
      </div>

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800">
              <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Batch</th>
              <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Client</th>
              <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Status</th>
              <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Files</th>
              <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Reviewer</th>
              <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Date</th>
              <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">Actions</th>
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
                <tr key={b.id} className="hover:bg-slate-800/30 transition-colors">
                  {/* Batch ID */}
                  <td className="px-4 py-3">
                    <div className="font-mono text-xs text-slate-300 max-w-[160px] truncate" title={b.parentBatchId}>
                      {b.parentBatchId}
                    </div>
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
                      <div className="flex items-start gap-1 mt-1.5" title={b.errorMessage}>
                        <AlertCircle size={10} className="text-red-400 flex-shrink-0 mt-0.5" />
                        <span className="text-[10px] text-red-400 leading-tight line-clamp-2 max-w-[120px]">
                          {b.errorMessage}
                        </span>
                      </div>
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
                    <div className="flex items-center gap-1.5">
                      {/* Run QC */}
                      {(b.status === "UPLOADED" || b.status === "VALIDATING" || b.status === "ERROR") && (
                        <button
                          onClick={() => handleProcessQC(b)}
                          disabled={isLoading}
                          className="h-7 px-2.5 rounded-md bg-indigo-900/50 hover:bg-indigo-800/60 border border-indigo-800/50 text-indigo-300 text-xs font-medium transition-colors disabled:opacity-40 flex items-center gap-1"
                        >
                          {isLoading ? (
                            <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                            </svg>
                          ) : null}
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
                          className="h-7 px-2.5 rounded-md border border-red-900/60 bg-red-950/30 hover:bg-red-950/60 text-red-300 text-xs font-medium transition-colors disabled:opacity-40 flex items-center gap-1"
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
                          <select
                            defaultValue=""
                            onChange={e => e.target.value && handleAssign(b.id, Number(e.target.value))}
                            disabled={isLoading}
                            className="h-7 bg-slate-800 border border-slate-700 text-slate-300 text-xs rounded-md px-2 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors disabled:opacity-40 max-w-[120px]"
                          >
                            <option value="">Assign…</option>
                            {reviewers.map(r => (
                              <option key={r.id} value={r.id}>{r.fullName ?? r.username}</option>
                            ))}
                          </select>
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
                        className="h-7 px-2 rounded-md hover:bg-red-950/40 text-slate-600 hover:text-red-400 text-xs transition-colors disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-slate-600"
                        title={b.status === "QC_PROCESSING" ? "Stop QC before deleting this batch" : "Delete batch"}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
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
    </div>
  );
}

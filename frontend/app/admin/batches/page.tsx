"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { Search, Plus, RefreshCw, ChevronLeft, ChevronRight, AlertCircle } from "lucide-react";
import {
  getAdminBatches, getUsers, processQC, assignReviewer, deleteBatch,
  getBatchStatus, getQCResults, reconcileStuckBatches,
  type Batch, type User,
} from "@/lib/api";
import StatusBadge from "@/components/shared/StatusBadge";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import UploadModal from "@/components/admin/UploadModal";
import { TableSkeleton } from "@/components/shared/Skeleton";
import EmptyState from "@/components/shared/EmptyState";
import { toast } from "@/lib/toast";
import { trackJob, updateJob, removeJob } from "@/lib/jobs";

const STATUSES = ["", "UPLOADED", "VALIDATING", "VALIDATION_FAILED", "QC_PROCESSING", "REVIEW_PENDING", "IN_REVIEW", "COMPLETED", "ERROR"];

// Per-batch QC progress tracker
interface BatchProgress {
  current: number;
  total: number;
}

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
  const pollingRef = useRef<Record<number, ReturnType<typeof setInterval>>>({});

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [bRes, uRes] = await Promise.all([
        getAdminBatches(page, statusFilter || undefined),
        getUsers(0),
      ]);
      setBatches(bRes.content);
      setTotalPages(bRes.totalPages);
      setReviewers(uRes.content.filter(u => u.role === "REVIEWER"));
    } catch {
      toast.error("Failed to load batches");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => { load(); }, [load]);

  // Start polling a batch that just entered QC_PROCESSING
  function startPolling(batch: Batch) {
    const batchId = batch.id;
    const jobKey = `qc-${batchId}`;
    const total = batch.files?.filter(f => f.fileType === "APPRAISAL").length ?? batch.files?.length ?? 0;

    trackJob({ id: jobKey, label: `QC: ${batch.parentBatchId}`, current: 0, total, batchId, startedAt: Date.now() });

    if (pollingRef.current[batchId]) return; // already polling

    const interval = setInterval(async () => {
      try {
        const [statusRes, results] = await Promise.all([
          getBatchStatus(batchId),
          getQCResults(batchId),
        ]);
        const done = results.length;
        updateJob(jobKey, done);
        setProgress(p => ({ ...p, [batchId]: { current: done, total } }));

        if (statusRes.status !== "QC_PROCESSING") {
          clearInterval(interval);
          delete pollingRef.current[batchId];
          removeJob(jobKey);
          setProgress(p => { const n = {...p}; delete n[batchId]; return n; });

          if (statusRes.status === "COMPLETED" || statusRes.status === "REVIEW_PENDING") {
            toast.success(`Batch "${batch.parentBatchId}" QC complete`, `${done} file${done !== 1 ? "s" : ""} processed`);
          } else if (statusRes.status === "ERROR") {
            toast.error(`Batch "${batch.parentBatchId}" failed`, "Check the error details in the batch list");
          }
          await load();
        }
      } catch { /* keep polling */ }
    }, 5000);

    pollingRef.current[batchId] = interval;
  }

  // Cleanup polling on unmount
  useEffect(() => {
    return () => { Object.values(pollingRef.current).forEach(clearInterval); };
  }, []);

  function setLoading1(id: number, on: boolean) {
    setActionLoading(prev => {
      const n = new Set(prev);
      on ? n.add(id) : n.delete(id);
      return n;
    });
  }

  async function handleProcessQC(batch: Batch) {
    setLoading1(batch.id, true);
    try {
      await processQC(batch.id);
      toast.info(`QC started for "${batch.parentBatchId}"`, "Processing files in the background");
      await load();
      // Find the updated batch and start polling
      const updated = { ...batch, status: "QC_PROCESSING" };
      startPolling(updated);
    } catch (e) {
      toast.error("QC trigger failed", String(e));
    } finally {
      setLoading1(batch.id, false);
    }
  }

  async function handleAssign(batchId: number, reviewerId: number) {
    setLoading1(batchId, true);
    try {
      await assignReviewer(batchId, reviewerId);
      toast.success("Reviewer assigned");
      await load();
    } catch (e) {
      toast.error("Assignment failed", String(e));
    } finally {
      setLoading1(batchId, false);
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
    setReconciling(true);
    try {
      const r = await reconcileStuckBatches();
      if (r.stuckFound === 0) toast.info("No stuck batches found");
      else toast.success("Reconciliation complete", r.message);
      if (r.retried > 0) await load();
    } catch (e) {
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
              const pct = prog && prog.total > 0 ? Math.round((prog.current / prog.total) * 100) : 0;

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
                          <span>{prog.current}/{prog.total} files</span>
                          <span className="font-mono">{pct}%</span>
                        </div>
                        <div className="w-24 h-1 bg-slate-800 rounded-full overflow-hidden">
                          <div className="h-full bg-indigo-500 rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
                        </div>
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
                  {/* Files */}
                  <td className="px-4 py-3 text-xs text-slate-400 tabular-nums">
                    {b.files?.length ?? 0}
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

                      {/* Assign reviewer */}
                      {(b.status === "REVIEW_PENDING" || b.status === "QC_PROCESSING") && reviewers.length > 0 && (
                        <select
                          defaultValue=""
                          onChange={e => e.target.value && handleAssign(b.id, Number(e.target.value))}
                          disabled={isLoading}
                          className="h-7 bg-slate-800 border border-slate-700 text-slate-300 text-xs rounded-md px-2 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors disabled:opacity-40 max-w-[110px]"
                        >
                          <option value="">Assign…</option>
                          {reviewers.map(r => (
                            <option key={r.id} value={r.id}>{r.fullName ?? r.username}</option>
                          ))}
                        </select>
                      )}

                      {/* Delete */}
                      <button
                        onClick={() => setDeleteTarget(b)}
                        className="h-7 px-2 rounded-md hover:bg-red-950/40 text-slate-600 hover:text-red-400 text-xs transition-colors"
                        title="Delete batch"
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

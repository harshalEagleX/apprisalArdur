"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  Search, Plus, RefreshCw, ChevronLeft, ChevronRight,
  FileStack, Clock3, CheckCircle2, Play, UserPlus, XCircle, AlertCircle,
} from "lucide-react";
import type { ComponentType } from "react";
import {
  getAdminBatches, deleteBatch,
  reconcileStuckBatches,
  bulkDeleteBatches, getSystemHealth,
  getBatchStatuses,
  type Batch,
} from "@/lib/api";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import UploadModal from "@/components/admin/UploadModal";
import BatchOrderViewToggle from "@/components/shared/BatchOrderViewToggle";
import { BatchRow } from "@/components/admin/BatchRow";
import { BatchRecoveryDrawer } from "@/components/admin/BatchRecoveryDrawer";
import { BatchHistoryDrawer } from "@/components/admin/BatchHistoryDrawer";
import { TableSkeleton } from "@/components/shared/Skeleton";
import EmptyState from "@/components/shared/EmptyState";
import { toast } from "@/lib/toast";

const STATUSES = [
  "", "UPLOADED", "VALIDATING", "VALIDATION_FAILED",
  "QC_PROCESSING", "REVIEW_PENDING", "IN_REVIEW", "COMPLETED", "ERROR",
];

type ReconcileResult = {
  stuckFound: number; retried: number; abandoned: number; pythonHealthy: boolean; message: string;
};


// ── Pill summary ──────────────────────────────────────────────────────────────
function SummaryPill({ icon: Icon, label, value, tone }: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string; value: number;
  tone: "slate" | "blue" | "indigo" | "amber" | "green";
}) {
  const tones = {
    slate: "border-white/10 bg-surface text-slate-300",
    blue:  "border-slate-900/50 bg-slate-950/30 text-slate-200",
    indigo:"border-slate-500/25 bg-slate-950/30 text-slate-200",
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
    slate: "border-white/10 bg-sunken/70 text-slate-300",
    amber: "border-amber-900/50 bg-amber-950/30 text-amber-200",
    blue:  "border-slate-900/50 bg-slate-950/30 text-slate-200",
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
    <div className="mb-4 rounded-lg border border-white/10 bg-surface p-4 shadow-[0_12px_32px_rgba(0,0,0,0.18)]">
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
  // Status filter options come from the backend (authoritative BatchStatus enum) so
  // the dropdown can never offer a value the backend would reject. The hardcoded
  // STATUSES list is only the initial/fallback set until the fetch resolves.
  const [statusOptions, setStatusOptions] = useState<string[]>(STATUSES.filter(Boolean));
  const [loading, setLoading]         = useState(true);
  const [showUpload, setShowUpload]   = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Batch | null>(null);
  const [recoveryTarget, setRecoveryTarget] = useState<Batch | null>(null);
  const [historyTarget, setHistoryTarget] = useState<Batch | null>(null);
  const [dbDegraded, setDbDegraded] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [reconcileResult, setReconcileResult] = useState<ReconcileResult | null>(null);
  const searchMountedRef              = useRef(false);

  // ── Bulk selection state ─────────────────────────────────────────────────
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkConfirmOpen, setBulkConfirmOpen] = useState(false);

  const handleSelect = useCallback((id: number, checked: boolean) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (checked) next.add(id); else next.delete(id);
      return next;
    });
  }, []);

  const handleSelectAll = useCallback((checked: boolean) => {
    setSelectedIds(checked ? new Set(batches.map(b => b.id)) : new Set());
  }, [batches]);

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  // Clear selection when the filter/page changes. setSelectedIds has stable identity
  // (guaranteed by useState), so this effect only re-runs when the filter changes.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { setSelectedIds(new Set()); }, [page, statusFilter, debouncedSearch]);

  const handleBulkDelete = useCallback(async () => {
    if (selectedIds.size === 0) return;
    setBulkConfirmOpen(false);
    setBulkLoading(true);
    try {
      const ids = Array.from(selectedIds);
      const { succeeded, failed } = await bulkDeleteBatches(ids);
      if (succeeded.length > 0) {
        setBatches(prev => prev.filter(b => !succeeded.includes(b.id)));
        toast.success(`Deleted ${succeeded.length} batch${succeeded.length > 1 ? "es" : ""}`);
      }
      if (failed.length > 0) toast.error(`Failed to delete ${failed.length} batch${failed.length > 1 ? "es" : ""}`);
      clearSelection();
    } catch {
      toast.error("Bulk delete failed");
    } finally {
      setBulkLoading(false);
    }
  }, [selectedIds, clearSelection]);


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
    setLoading(true);
    try {
      const bRes = await getAdminBatches(page, statusFilter || undefined, debouncedSearch || undefined);
      setBatches(bRes.content);
      setTotalPages(bRes.totalPages);
      setTotalElements(Number(bRes.totalElements ?? bRes.content.length));
    } catch (e) {
      toast.error("Failed to load batches", e instanceof Error ? e.message : undefined);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, debouncedSearch]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  // Load the authoritative status list from the backend once on mount.
  useEffect(() => {
    let cancelled = false;
    getBatchStatuses()
      .then(list => { if (!cancelled && Array.isArray(list) && list.length) setStatusOptions(list); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  // Sync URL params
  useEffect(() => {
    const params = new URLSearchParams();
    if (statusFilter) params.set("status", statusFilter);
    if (debouncedSearch) params.set("search", debouncedSearch);
    if (page > 0) params.set("page", String(page));
    window.history.replaceState(null, "", params.toString() ? `/admin/batches?${params}` : "/admin/batches");
  }, [debouncedSearch, page, statusFilter]);


  // Poll DB connection-pool health so an admin sees a "system under load" banner
  // before operations start timing out. The backend still degrades gracefully on
  // its own; this is a proactive heads-up, not the failure handler.
  useEffect(() => {
    let cancelled = false;
    const check = () => {
      getSystemHealth()
        .then(h => { if (!cancelled) setDbDegraded(Boolean(h.degraded)); })
        .catch(() => { /* health probe is best-effort; ignore transient errors */ });
    };
    check();
    const timer = window.setInterval(check, 30_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  useEffect(() => {
    if (loading) return;
  }, [batches, loading, page, totalElements]);

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
    <div className="w-full max-w-[1800px] p-6">
      {dbDegraded && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-950/30 px-4 py-2.5">
          <AlertCircle size={15} className="shrink-0 text-amber-400" />
          <span className="text-sm text-amber-200">
            System under load — database connections are saturated. Uploads and QC runs may be slow or briefly queue; they are not lost.
          </span>
        </div>
      )}
      {/* Header */}
      <div className="flex flex-col gap-4 mb-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2"><BatchOrderViewToggle active="batch" /></div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600">Document intake</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-white">Batches</h1>
          <p className="mt-1 text-sm text-slate-500">
            Upload, validate, process, assign, and recover appraisal document sets. Batch status reflects the
            upload/QC pipeline — switch to Order view for each order&apos;s own lifecycle status.
          </p>
        </div>
        <div data-guide="admin-batches-actions" className="flex flex-wrap items-center gap-2">
          <button onClick={handleReconcile} disabled={reconciling} title="Find and recover batches stuck in QC_PROCESSING"
            className="inline-flex h-9 items-center gap-1.5 rounded-md border border-white/10 bg-surface px-3 text-sm text-slate-300 transition-colors hover:border-white/15 hover:bg-white/[0.04] hover:text-white disabled:opacity-50">
            <RefreshCw size={13} className={reconciling ? "animate-spin" : ""} />
            Reconcile
          </button>
          <button onClick={() => {
            setShowUpload(true);
          }}
            className="inline-flex h-9 items-center gap-1.5 rounded-md border border-slate-400/30 bg-slate-600 px-4 text-sm font-semibold text-white shadow-[0_0_22px_rgba(226,232,240,0.16)] transition-colors hover:bg-slate-500">
            <Plus size={14} /> Upload batch
          </button>
        </div>
      </div>

      {/* Summary pills */}
      <div data-guide="admin-batches-summary" className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
        <SummaryPill icon={FileStack}    label="On page"      value={pageStats.total}     tone="slate"  />
        <SummaryPill icon={Clock3}       label="QC running"   value={pageStats.running}   tone="indigo" />
        <SummaryPill icon={UserPlus}     label="Needs review" value={pageStats.review}    tone="amber"  />
        <SummaryPill icon={Play}         label="Ready / retry"value={pageStats.ready}     tone="blue"   />
        <SummaryPill icon={CheckCircle2} label="Completed"    value={pageStats.completed} tone="green"  />
      </div>

      {/* Filters */}
      <div data-guide="admin-batches-filters" className="mb-4 rounded-lg border border-white/10 bg-surface/95 p-3 shadow-[0_12px_32px_rgba(0,0,0,0.16)]">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative w-full sm:max-w-sm">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Search all batches by ID or client…"
                className="h-9 w-full rounded-md border border-white/10 bg-sunken/70 pl-8 pr-3 text-sm text-white placeholder-slate-600 transition-colors focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30" />
            </div>
            <select value={statusFilter} onChange={e => { setStatus(e.target.value); setPage(0); }}
              className="h-9 w-full rounded-md border border-white/10 bg-sunken/70 px-3 text-sm text-slate-300 transition-colors focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30 sm:w-48"
              aria-label="Filter by status">
              <option value="">All statuses</option>
              {statusOptions.map(s => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </select>
            {(search || statusFilter) && (
              <button onClick={() => { setSearch(""); setStatus(""); setPage(0); }}
                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-white/10 bg-sunken/70 px-3 text-sm text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white">
                <XCircle size={13} /> Clear
              </button>
            )}
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
          <span>Showing {batches.length} of {totalElements} matching row{totalElements === 1 ? "" : "s"} on page {page + 1}</span>
          <span className="hidden h-1 w-1 rounded-full bg-slate-700 sm:inline-block" />
          <span>{activeFilterLabel}</span>
          {debouncedSearch && <span>Global search <span className="rounded border border-white/10 bg-muted px-1.5 py-0.5 font-mono text-slate-400">{debouncedSearch}</span></span>}
        </div>
      </div>

      {reconcileResult && <ReconcileSummary result={reconcileResult} onDismiss={() => setReconcileResult(null)} />}

      {/* Bulk-action toolbar — visible only when rows are selected */}
      {selectedIds.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-indigo-500/25 bg-indigo-950/20 px-4 py-2.5 shadow-[0_4px_16px_rgba(0,0,0,0.18)]">
          <span className="text-sm font-medium text-indigo-300">
            {selectedIds.size} batch{selectedIds.size > 1 ? "es" : ""} selected
          </span>
          <span className="mx-1 h-4 w-px bg-white/10" />
          <button
            onClick={() => setBulkConfirmOpen(true)}
            disabled={bulkLoading}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-red-500/25 bg-red-950/30 px-3 text-xs font-medium text-red-300 transition-colors hover:bg-red-950/60 disabled:opacity-40"
          >
            <XCircle size={12} /> Delete selected
          </button>
          <button
            onClick={clearSelection}
            disabled={bulkLoading}
            className="ml-auto text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            Clear selection
          </button>
        </div>
      )}

      {/* Table */}
      <div data-guide="admin-batches-table" className="overflow-hidden rounded-lg border border-white/10 bg-surface shadow-[0_16px_40px_rgba(0,0,0,0.2)]">
        <div className="data-scroll">
          <table className="w-full min-w-[1120px] text-sm">
            <thead>
              <tr className="border-b border-white/10 bg-sunken/80">
                {/* Select-all checkbox */}
                <th className="sticky top-0 z-10 w-10 bg-sunken px-3 py-3">
                  <input
                    type="checkbox"
                    checked={batches.length > 0 && selectedIds.size === batches.length}
                    ref={el => {
                      if (el) el.indeterminate = selectedIds.size > 0 && selectedIds.size < batches.length;
                    }}
                    onChange={e => handleSelectAll(e.target.checked)}
                    className="h-4 w-4 rounded border-white/20 bg-surface accent-indigo-500 cursor-pointer"
                    aria-label="Select all batches"
                    disabled={batches.length === 0}
                  />
                </th>
                {["Batch", "Client", "Status", "Files", "Reviewer", "Date", "Actions"].map((h, i) => (
                  <th key={h} className={`sticky top-0 z-10 bg-sunken px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500 ${i === 6 ? "text-right" : "text-left"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {loading ? (
                <tr><td colSpan={8} className="p-0"><TableSkeleton rows={6} cols={8} /></td></tr>
              ) : batches.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <EmptyState
                      icon={Search}
                      title={debouncedSearch || statusFilter ? "No batches match your filters" : "No batches yet"}
                      description={!debouncedSearch && !statusFilter ? "Upload a ZIP archive to get started." : undefined}
                      action={!debouncedSearch && !statusFilter ? (
                        <button onClick={() => setShowUpload(true)} className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-300 transition-colors">
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
                  isLoading={bulkLoading}
                  progress={undefined}
                  onDelete={setDeleteTarget}
                  onOpenRecovery={setRecoveryTarget}
                  onOpenHistory={setHistoryTarget}
                  selected={selectedIds.has(b.id)}
                  onSelect={handleSelect}
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
        onUploaded={(batchId, ref, fileCount) => {
          toast.success(`Batch "${ref}" uploaded`, `${fileCount} files ready for QC`);
          void load();
        }} />
      {/* Copy matches what the API actually does: deleteBatch() soft-deletes, so
          the batch leaves the workspace but its files, QC results and audit trail
          are retained. Both dialogs used to promise an irreversible purge. */}
      <ConfirmDialog open={!!deleteTarget} title="Delete batch"
        message={`Remove "${deleteTarget?.parentBatchId}" and its files from the workspace? It disappears from every list and its orders stop being processed. The records and audit trail are retained, so support can restore it.`}
        confirmLabel="Delete batch" danger confirmationText={deleteTarget?.parentBatchId}
        onConfirm={handleDelete} onCancel={() => setDeleteTarget(null)} />
      <ConfirmDialog open={bulkConfirmOpen} title={`Delete ${selectedIds.size} batch${selectedIds.size === 1 ? "" : "es"}`}
        message={`Remove ${selectedIds.size} selected batch${selectedIds.size === 1 ? "" : "es"} and their files from the workspace? They disappear from every list and their orders stop being processed. The records and audit trail are retained, so support can restore them.`}
        confirmLabel={`Delete ${selectedIds.size} batch${selectedIds.size === 1 ? "" : "es"}`} danger
        onConfirm={() => void handleBulkDelete()} onCancel={() => setBulkConfirmOpen(false)} />
      <BatchRecoveryDrawer
        batch={recoveryTarget}
        busy={bulkLoading}
        onClose={() => setRecoveryTarget(null)}
        onDelete={batch => { setRecoveryTarget(null); setDeleteTarget(batch); }}
        onReupload={() => { setRecoveryTarget(null); setShowUpload(true); }}
      />
      <BatchHistoryDrawer
        batch={historyTarget}
        onClose={() => setHistoryTarget(null)}
      />
    </div>
  );
}

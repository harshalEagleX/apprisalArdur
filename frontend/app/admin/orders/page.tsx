"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Search, RefreshCw, ChevronLeft, ChevronRight, ClipboardList,
  CheckCircle2, AlertCircle, Clock, XCircle, History, Play, UserPlus, Sparkles,
} from "lucide-react";
import {
  getOrders, getOrderStatuses, runOrderBackfill, getAllUsers,
  processOrdersQC, bulkAssignOrderReviewer, autoAssignOrders,
  getOrderQCProgress,
  type OrderSummary, type User,
} from "@/lib/api";
import { TableSkeleton } from "@/components/shared/Skeleton";
import EmptyState from "@/components/shared/EmptyState";
import StatusBadge from "@/components/shared/StatusBadge";
import BatchOrderViewToggle from "@/components/shared/BatchOrderViewToggle";
import ActivityMonitor from "@/components/shared/ActivityMonitor";
import { trackJob, updateJob, removeJob } from "@/lib/jobs";
import { toast } from "@/lib/toast";

const STATUSES = ["", "INCOMPLETE", "UNMATCHED", "READY_FOR_QC", "QC_PROCESSING", "NEEDS_REVIEW", "COMPLETED", "ERROR"];

function SummaryPill({ icon: Icon, label, value, tone }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string; value: number;
  tone: "slate" | "amber" | "green" | "red";
}) {
  const tones = {
    slate: "border-white/10 bg-[#11161C] text-slate-300",
    amber: "border-amber-900/50 bg-amber-950/30 text-amber-200",
    green: "border-green-900/50 bg-green-950/30 text-green-200",
    red:   "border-red-900/50 bg-red-950/30 text-red-200",
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

export default function OrdersPage() {
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [totalElements, setTotalElements] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [statusOptions, setStatusOptions] = useState<string[]>(STATUSES.filter(Boolean));
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebounced] = useState("");
  const [backfillRunning, setBackfillRunning] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [reviewers, setReviewers] = useState<User[]>([]);
  const [assignReviewerId, setAssignReviewerId] = useState<string>("");
  const [actionRunning, setActionRunning] = useState(false);
  // Job ids currently shown in the background-activity dock (one per running order).
  const jobIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  // `silent` reloads (used by the QC auto-poll) refresh the rows without flashing
  // the skeleton or firing a toast on a transient failure.
  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    try {
      const res = await getOrders(page, statusFilter || undefined, debouncedSearch || undefined);
      setOrders(res.content);
      setTotalPages(res.totalPages);
      setTotalElements(Number(res.totalElements ?? res.content.length));
    } catch {
      if (!opts?.silent) toast.error("Failed to load orders");
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, [page, statusFilter, debouncedSearch]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    getOrderStatuses().then(list => { if (Array.isArray(list) && list.length) setStatusOptions(list); }).catch(() => undefined);
  }, []);

  useEffect(() => {
    getAllUsers().then(list => setReviewers(list.filter(u => u.role === "REVIEWER"))).catch(() => undefined);
  }, []);

  // Stable key of the orders currently in QC. Drives the auto-poll below: while
  // it is non-empty we keep refreshing so "QC Running" flips to "Needs Review"
  // on its own, instead of stranding a stale snapshot until a manual Refresh.
  const runningKey = orders
    .filter(o => o.documentStatus === "QC_PROCESSING")
    .map(o => o.id)
    .sort((a, b) => a - b)
    .join(",");

  // Reconcile the bottom-right activity dock with the set of running orders:
  // seed a job when an order starts QC, drop it the moment QC finishes.
  useEffect(() => {
    const wanted = new Map<string, OrderSummary>(
      orders
        .filter(o => o.documentStatus === "QC_PROCESSING")
        .map(o => [`order-qc-${o.id}`, o] as [string, OrderSummary]),
    );
    jobIdsRef.current.forEach(jid => { if (!wanted.has(jid)) removeJob(jid); });
    wanted.forEach((o, jid) => {
      if (!jobIdsRef.current.has(jid)) {
        trackJob({
          id: jid,
          batchId: 0,
          startedAt: Date.now(),
          label: `QC · ${o.transactionRef}`,
          current: 0,
          total: o.activeDocumentCount || 1,
          unitLabel: "docs",
          message: "Processing…",
        });
      }
    });
    jobIdsRef.current = new Set(wanted.keys());
  }, [orders]);

  // Poll per-order QC progress + silently refresh the list while anything runs.
  useEffect(() => {
    if (!runningKey) return;
    const ids = runningKey.split(",").map(Number);
    let stop = false;
    async function tick() {
      await Promise.all(ids.map(async oid => {
        try {
          const p = await getOrderQCProgress(oid);
          if (stop) return;
          updateJob(`order-qc-${oid}`, p.current ?? 0, p.total, {
            smoothedPercent: p.smoothedPercent ?? p.percent,
            subStage: p.subStage ?? null,
            subMessage: p.subMessage ?? null,
            message: p.message,
          });
        } catch { /* transient — keep polling */ }
      }));
      if (stop) return;
      await load({ silent: true });
    }
    const timer = window.setInterval(tick, 2000);
    return () => { stop = true; window.clearInterval(timer); };
  }, [runningKey, load]);

  // Leaving the page clears any dock jobs this page put up.
  useEffect(() => () => {
    jobIdsRef.current.forEach(jid => removeJob(jid));
    jobIdsRef.current = new Set();
  }, []);

  // Drop selections for rows no longer on the page (filter/page change).
  useEffect(() => {
    setSelected(prev => {
      const visible = new Set(orders.map(o => o.id));
      const next = new Set([...prev].filter(id => visible.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [orders]);

  const selectedIds = Array.from(selected);
  const allOnPageSelected = orders.length > 0 && orders.every(o => selected.has(o.id));

  function toggleOne(id: number) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  function toggleAll() {
    setSelected(prev => (allOnPageSelected ? new Set() : new Set(orders.map(o => o.id))));
  }

  async function handleRunQCSelected() {
    if (!selectedIds.length) return;
    setActionRunning(true);
    try {
      const res = await processOrdersQC(selectedIds);
      const started = res.startedOrderIds?.length ?? 0;
      if (started > 0) {
        toast.success("QC started", `${started} order(s) queued.`);
      } else {
        toast.info("Nothing started", res.message || "Selected order(s) may already be processing.");
      }
      setSelected(new Set());
      void load();
    } catch (e) {
      toast.error("Failed to start QC", String(e));
    } finally {
      setActionRunning(false);
    }
  }

  async function handleAssignSelected() {
    if (!selectedIds.length) return;
    const reviewerId = assignReviewerId ? Number(assignReviewerId) : null;
    if (reviewerId === null) { toast.error("Pick a reviewer first"); return; }
    setActionRunning(true);
    try {
      const res = await bulkAssignOrderReviewer(selectedIds, reviewerId);
      toast.success("Reviewer assigned", `${res.assignedCount} order(s) allocated.`);
      setSelected(new Set());
      void load();
    } catch (e) {
      toast.error("Assignment failed", String(e));
    } finally {
      setActionRunning(false);
    }
  }

  async function handleAutoAssign() {
    setActionRunning(true);
    try {
      const res = await autoAssignOrders(selectedIds.length ? selectedIds : undefined);
      toast.success("Auto-assign complete", res.message);
      setSelected(new Set());
      void load();
    } catch (e) {
      toast.error("Auto-assign failed", String(e));
    } finally {
      setActionRunning(false);
    }
  }

  async function handleBackfill() {
    setBackfillRunning(true);
    try {
      const result = await runOrderBackfill();
      toast.success(
        `Backfill complete`,
        `${result.filesProcessed} file(s) processed — ${result.ordersCreated} new order(s), ${result.duplicatesFound} duplicate(s) linked.`
      );
      void load();
    } catch (e) {
      toast.error("Backfill failed", String(e));
    } finally {
      setBackfillRunning(false);
    }
  }

  const stats = {
    total: orders.length,
    needsReview: orders.filter(o => o.documentStatus === "NEEDS_REVIEW").length,
    completed: orders.filter(o => o.documentStatus === "COMPLETED").length,
    unmatched: orders.filter(o => o.documentStatus === "UNMATCHED").length,
  };

  return (
    <div className="w-full max-w-[1800px] p-6">
      <div className="flex flex-col gap-4 mb-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2"><BatchOrderViewToggle active="order" /></div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600">Order tracking</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-white">Orders</h1>
          <p className="mt-1 text-sm text-slate-500">
            One row per real-world order — documents, QC result, and lifecycle status, regardless of which
            batch(es) it was uploaded through. Order status is tracked separately from Batch status.
          </p>
        </div>
        <button
          onClick={handleBackfill}
          disabled={backfillRunning}
          title="Link pre-existing files with no resolved order (one-time, safe to re-run)"
          className="inline-flex h-9 items-center gap-1.5 rounded-md border border-white/10 bg-[#11161C] px-3 text-sm text-slate-300 transition-colors hover:border-white/15 hover:bg-white/[0.04] hover:text-white disabled:opacity-50"
        >
          <History size={13} className={backfillRunning ? "animate-spin" : ""} />
          {backfillRunning ? "Reconciling…" : "Reconcile legacy files"}
        </button>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <SummaryPill icon={ClipboardList} label="On page" value={stats.total} tone="slate" />
        <SummaryPill icon={Clock} label="Needs review" value={stats.needsReview} tone="amber" />
        <SummaryPill icon={CheckCircle2} label="Completed" value={stats.completed} tone="green" />
        <SummaryPill icon={AlertCircle} label="Unmatched" value={stats.unmatched} tone="red" />
      </div>

      <div className="mb-4 rounded-lg border border-white/10 bg-[#11161C]/95 p-3 shadow-[0_12px_32px_rgba(0,0,0,0.16)]">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative w-full sm:max-w-sm">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Search by order ref or property address…"
                className="h-9 w-full rounded-md border border-white/10 bg-[#0B0F14]/70 pl-8 pr-3 text-sm text-white placeholder-slate-600 transition-colors focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30" />
            </div>
            <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(0); }}
              className="h-9 w-full rounded-md border border-white/10 bg-[#0B0F14]/70 px-3 text-sm text-slate-300 transition-colors focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30 sm:w-48"
              aria-label="Filter by document status">
              <option value="">All statuses</option>
              {statusOptions.map(s => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </select>
            {(search || statusFilter) && (
              <button onClick={() => { setSearch(""); setStatusFilter(""); setPage(0); }}
                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-white/10 bg-[#0B0F14]/70 px-3 text-sm text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white">
                <XCircle size={13} /> Clear
              </button>
            )}
          </div>
          <button onClick={() => load()} className="flex h-9 items-center gap-1.5 rounded-md border border-white/10 bg-[#0B0F14]/70 px-3 text-sm text-slate-400 transition-colors hover:text-white">
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
        <div className="mt-2 text-[11px] text-slate-500">
          Showing {orders.length} of {totalElements} matching order{totalElements === 1 ? "" : "s"} on page {page + 1}
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-white/10 bg-[#11161C]/95 px-3 py-2">
        <span className="text-xs text-slate-400">
          {selectedIds.length > 0 ? `${selectedIds.length} selected` : "Select orders to run QC or assign a reviewer"}
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button
            onClick={handleRunQCSelected}
            disabled={actionRunning || selectedIds.length === 0}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-indigo-500/40 bg-indigo-500/10 px-3 text-sm text-indigo-200 transition-colors hover:bg-indigo-500/20 disabled:opacity-40"
          >
            <Play size={13} /> Run QC{selectedIds.length > 1 ? ` (${selectedIds.length})` : ""}
          </button>
          <div className="flex items-center gap-1">
            <select
              value={assignReviewerId}
              onChange={e => setAssignReviewerId(e.target.value)}
              aria-label="Reviewer to assign"
              className="h-8 rounded-md border border-white/10 bg-[#0B0F14]/70 px-2 text-sm text-slate-300 focus:border-slate-500/70 focus:outline-none"
            >
              <option value="">Reviewer…</option>
              {reviewers.map(r => <option key={r.id} value={r.id}>{r.fullName || r.username}</option>)}
            </select>
            <button
              onClick={handleAssignSelected}
              disabled={actionRunning || selectedIds.length === 0 || !assignReviewerId}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-white/10 bg-[#0B0F14]/70 px-3 text-sm text-slate-300 transition-colors hover:bg-white/[0.05] hover:text-white disabled:opacity-40"
            >
              <UserPlus size={13} /> Assign
            </button>
          </div>
          <button
            onClick={handleAutoAssign}
            disabled={actionRunning}
            title="System balances unassigned orders across reviewers (only runs when clicked)"
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-white/10 bg-[#0B0F14]/70 px-3 text-sm text-slate-300 transition-colors hover:bg-white/[0.05] hover:text-white disabled:opacity-40"
          >
            <Sparkles size={13} /> Auto-assign{selectedIds.length ? ` (${selectedIds.length})` : ""}
          </button>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-white/10 bg-[#11161C] shadow-[0_16px_40px_rgba(0,0,0,0.2)]">
        <div className="data-scroll">
          <table className="w-full min-w-[1000px] text-sm">
            <thead>
              <tr className="border-b border-white/10 bg-[#0B0F14]/80">
                <th className="sticky top-0 z-10 bg-[#0B0F14] px-4 py-3 text-left">
                  <input type="checkbox" checked={allOnPageSelected} onChange={toggleAll}
                    aria-label="Select all orders on page"
                    className="h-3.5 w-3.5 cursor-pointer accent-indigo-500" />
                </th>
                {["Order", "Client", "Property", "Status", "Documents", "Reviewer", "Updated"].map(h => (
                  <th key={h} className="sticky top-0 z-10 bg-[#0B0F14] px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {loading ? (
                <tr><td colSpan={8} className="p-0"><TableSkeleton rows={6} cols={8} /></td></tr>
              ) : orders.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <EmptyState
                      icon={Search}
                      title={debouncedSearch || statusFilter ? "No orders match your filters" : "No orders yet"}
                      description={!debouncedSearch && !statusFilter ? "Orders are created automatically when a batch is uploaded." : undefined}
                    />
                  </td>
                </tr>
              ) : orders.map(o => (
                <tr key={o.id} className={`transition-colors hover:bg-white/[0.025] ${selected.has(o.id) ? "bg-indigo-500/[0.06]" : ""}`}>
                  <td className="px-4 py-3">
                    <input type="checkbox" checked={selected.has(o.id)} onChange={() => toggleOne(o.id)}
                      aria-label={`Select order ${o.transactionRef}`}
                      className="h-3.5 w-3.5 cursor-pointer accent-indigo-500" />
                  </td>
                  <td className="px-4 py-3">
                    <Link href={`/admin/orders/${o.id}`} className="font-mono text-sm font-medium text-slate-200 hover:text-indigo-300">
                      {o.transactionRef}
                    </Link>
                    {o.revisionNumber > 0 && (
                      <span className="ml-2 rounded border border-white/10 bg-[#161B22] px-1.5 py-0.5 text-[10px] text-slate-500">rev {o.revisionNumber}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-400">{o.client?.name ?? "—"}</td>
                  <td className="px-4 py-3 max-w-[280px] truncate text-slate-400" title={o.propertyAddress ?? undefined}>
                    {o.propertyAddress ?? "—"}
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={o.documentStatus} /></td>
                  <td className="px-4 py-3 tabular-nums text-slate-400">{o.activeDocumentCount}</td>
                  <td className="px-4 py-3 text-slate-400">
                    {o.assignedReviewer
                      ? <span className="text-slate-300">{o.assignedReviewer.fullName || o.assignedReviewer.username}</span>
                      : <span className="text-slate-600">Unassigned</span>}
                  </td>
                  <td className="px-4 py-3 text-[11px] text-slate-500">
                    {o.updatedAt ? new Date(o.updatedAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

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

      {/* Background-activity dock — shows live order-QC progress bottom-right. */}
      <ActivityMonitor />
    </div>
  );
}

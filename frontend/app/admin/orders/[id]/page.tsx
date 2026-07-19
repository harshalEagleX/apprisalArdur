"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, ChevronRight, ClipboardList, FileText, Package,
  RefreshCw, History, Play, UserPlus, Trash2, Check, Minus, AlertTriangle, Square, Clock,
} from "lucide-react";
import {
  getOrderById, getAllUsers, processOrderQC, assignOrderReviewer, deleteOrder, getReviewerLoad,
  getOrderQCProgress, cancelOrderQC,
  type OrderDetail, type User, type QCProgressSnapshot,
} from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import { Skeleton, TableSkeleton } from "@/components/shared/Skeleton";
import StatusBadge from "@/components/shared/StatusBadge";
import { toast } from "@/lib/toast";

function formatDuration(seconds?: number | null): string | null {
  if (seconds == null || seconds < 0) return null;
  if (seconds < 60) return `${seconds}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function formatDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

function fileTypeLabel(t: string): string {
  switch (t) {
    case "APPRAISAL": return "Appraisal";
    case "APPRAISAL_XML": return "Appraisal XML";
    case "ENGAGEMENT": return "Engagement";
    case "CONTRACT": return "Contract";
    default: return t;
  }
}

export default function OrderDetailPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [reviewers, setReviewers] = useState<User[]>([]);
  const [actionRunning, setActionRunning] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [reviewerLoad, setReviewerLoad] = useState<Record<number, number>>({});
  const [loadAverage, setLoadAverage] = useState(0);
  const [qcProgress, setQcProgress] = useState<QCProgressSnapshot | null>(null);
  const [qcRunning, setQcRunning] = useState(false);
  const router = useRouter();

  const refreshLoad = useCallback(() => {
    getReviewerLoad().then(r => {
      const map: Record<number, number> = {};
      r.loads.forEach(l => { map[l.reviewerId] = l.count; });
      setReviewerLoad(map);
      setLoadAverage(r.average);
    }).catch(() => undefined);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const o = await getOrderById(id);
      setOrder(o);
      // Resume the live bar if the order is already mid-QC when we (re)load it.
      if (o.documentStatus === "QC_PROCESSING") setQcRunning(true);
    } catch {
      toast.error("Failed to load order");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    getAllUsers().then(list => setReviewers(list.filter(u => u.role === "REVIEWER"))).catch(() => undefined);
    refreshLoad();
  }, [refreshLoad]);

  // Live QC progress: WebSocket push is primary, polling is the fallback. Both feed the
  // same qcProgress state; qcRunning drives the progress bar + Run/Cancel toggle.
  useWebSocket(
    qcRunning ? [`/topic/qc/order/${id}/progress`] : [],
    (_topic, payload) => {
      const p = payload as QCProgressSnapshot;
      setQcProgress(p);
      if (p.running === false && p.stage !== "queued") { setQcRunning(false); void load(); }
    },
  );

  useEffect(() => {
    if (!qcRunning) return;
    let stop = false;
    let timer = window.setTimeout(tick, 1500);
    async function tick() {
      try {
        const p = await getOrderQCProgress(id);
        if (stop) return;
        setQcProgress(p);
        if (p.running === false && p.stage !== "queued" && p.stage !== "idle") {
          setQcRunning(false);
          void load();
          return;
        }
      } catch { /* transient — keep polling */ }
      if (!stop) timer = window.setTimeout(tick, 2000);
    }
    return () => { stop = true; window.clearTimeout(timer); };
  }, [qcRunning, id, load]);

  async function handleRunQC() {
    setActionRunning(true);
    try {
      const res = await processOrderQC(id);
      if ((res.startedOrderIds?.length ?? 0) > 0) {
        toast.success("QC started for this order.");
        setQcProgress({ stage: "queued", message: "QC job queued", current: 0, total: 1, percent: 0, running: true });
        setQcRunning(true);
      } else {
        toast.info("Nothing started", res.message || "Order may already be processing.");
      }
      void load();
    } catch (e) {
      toast.error("Failed to start QC", String(e));
    } finally {
      setActionRunning(false);
    }
  }

  async function handleCancelQC() {
    try {
      const res = await cancelOrderQC(id);
      toast.info(res.cancelled ? "QC stop requested" : "QC is not running", "");
      setQcRunning(false);
      void load();
    } catch (e) {
      toast.error("Failed to stop QC", String(e));
    }
  }

  async function handleAssign(value: string) {
    const reviewerId = value ? Number(value) : null;
    setActionRunning(true);
    try {
      await assignOrderReviewer(id, reviewerId);
      if (reviewerId != null) {
        const after = (reviewerLoad[reviewerId] ?? 0) + 1;
        // Non-blocking fairness hint: warn when this reviewer is now clearly above the team average.
        if (loadAverage > 0 && after > loadAverage + 1.5) {
          const r = reviewers.find(x => x.id === reviewerId);
          toast.info("Uneven load",
            `${r?.fullName || r?.username || "This reviewer"} now has ${after} orders — above the team average of ${loadAverage.toFixed(1)}. Consider Auto-assign to rebalance.`);
        } else {
          toast.success("Reviewer assigned.");
        }
      } else {
        toast.success("Reviewer cleared.");
      }
      void load();
      refreshLoad();
    } catch (e) {
      toast.error("Assignment failed", String(e));
    } finally {
      setActionRunning(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      const res = await deleteOrder(id);
      toast.success("Order deleted", `${res.deletedFiles} document(s) removed.`);
      router.push("/admin/orders");
    } catch (e) {
      toast.error("Delete failed", String(e));
      setDeleting(false);
      setConfirmDelete(false);
    }
  }

  const activeDocs = order?.documents.filter(d => d.active) ?? [];
  const historicalDocs = order?.documents.filter(d => !d.active) ?? [];
  // An order can only be assigned to a reviewer once its QC is done.
  const qcDone = order?.documentStatus === "NEEDS_REVIEW" || order?.documentStatus === "COMPLETED";

  return (
    <div className="w-full max-w-[1400px] p-6 lg:p-8">
      <nav className="mb-4 flex items-center gap-1.5 text-xs text-slate-500">
        <Link href="/admin/orders" className="inline-flex items-center gap-1 transition-colors hover:text-slate-300">
          <ArrowLeft size={12} /> Orders
        </Link>
        <ChevronRight size={12} className="text-slate-600" />
        <span className="text-slate-300 truncate max-w-[320px]">
          {loading ? "Loading…" : order?.transactionRef ?? `Order #${id}`}
        </span>
      </nav>

      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-muted">
            <ClipboardList size={18} className="text-slate-400" />
          </div>
          <div className="min-w-0">
            {loading ? <Skeleton className="h-6 w-64" /> : (
              <h1 className="font-mono text-lg font-semibold text-white">{order?.transactionRef}</h1>
            )}
            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              {order?.client && <span>{order.client.name}</span>}
              {order?.propertyAddress && (<><span className="text-slate-700">·</span><span>{order.propertyAddress}</span></>)}
              {order?.revisionNumber ? (<><span className="text-slate-700">·</span><span>revision {order.revisionNumber}</span></>) : null}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {order?.documentStatus && <StatusBadge status={order.documentStatus} />}
          {qcRunning ? (
            <button onClick={handleCancelQC}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-red-500/40 bg-red-500/10 px-3 text-xs text-red-300 transition-colors hover:bg-red-500/20">
              <Square size={12} /> Stop QC
            </button>
          ) : (
            <button onClick={handleRunQC} disabled={actionRunning}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-indigo-500/40 bg-indigo-500/10 px-3 text-xs text-indigo-200 transition-colors hover:bg-indigo-500/20 disabled:opacity-40">
              <Play size={12} /> Run QC
            </button>
          )}
          <div className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-surface px-2"
               title={qcDone ? undefined : "This order can be assigned to a reviewer only after its QC is done."}>
            <UserPlus size={12} className="text-slate-500" />
            <select
              value={order?.assignedReviewer?.id ?? ""}
              onChange={e => handleAssign(e.target.value)}
              disabled={actionRunning || !qcDone}
              aria-label="Assign reviewer"
              className="h-8 bg-transparent pr-1 text-xs text-slate-300 focus:outline-none disabled:opacity-40"
            >
              <option value="">Unassigned</option>
              {reviewers.map(r => {
                const c = reviewerLoad[r.id];
                return (
                  <option key={r.id} value={r.id}>
                    {(r.fullName || r.username)}{c !== undefined ? ` · ${c} order${c === 1 ? "" : "s"}` : ""}
                  </option>
                );
              })}
            </select>
          </div>
          <button onClick={() => load()} className="flex h-8 items-center gap-1.5 rounded-md border border-white/10 bg-surface px-3 text-xs text-slate-400 transition-colors hover:text-white">
            <RefreshCw size={12} /> Refresh
          </button>
          <button onClick={() => setConfirmDelete(true)} disabled={actionRunning || loading}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-red-500/30 bg-red-500/10 px-3 text-xs text-red-300 transition-colors hover:bg-red-500/20 disabled:opacity-40">
            <Trash2 size={12} /> Delete
          </button>
        </div>
      </header>

      {qcRunning && (
        <div className="mb-6 rounded-xl border border-indigo-500/25 bg-indigo-950/20 p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-semibold text-indigo-200">
              <RefreshCw size={13} className="animate-spin" />
              {qcProgress?.message || "Running QC…"}
            </div>
            <span className="tabular-nums text-[11px] text-indigo-300/80">
              {Math.round(qcProgress?.smoothedPercent ?? qcProgress?.percent ?? 0)}%
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div className="h-full rounded-full bg-indigo-400 transition-all duration-500"
                 style={{ width: `${Math.max(4, Math.round(qcProgress?.smoothedPercent ?? qcProgress?.percent ?? 0))}%` }} />
          </div>
          {qcProgress?.subMessage && (
            <div className="mt-1.5 truncate text-[11px] text-slate-400">{qcProgress.subMessage}</div>
          )}
        </div>
      )}

      {order?.activeQcResult && (
        <div className="mb-6 rounded-xl border border-white/10 bg-surface p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Active QC result</div>
            <Link href={`/qc-review?id=${order.activeQcResult.id}`} className="text-[11px] text-indigo-300 hover:text-indigo-200">
              View rules ↗
            </Link>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={order.activeQcResult.finalDecision ?? order.activeQcResult.qcDecision} />
            <span className="tabular-nums text-[12px] text-slate-400">
              {order.activeQcResult.passedCount} pass · {order.activeQcResult.failedCount} fail · {order.activeQcResult.verifyCount} review ·
              {" "}{order.activeQcResult.totalRules} rules
            </span>
          </div>

          {/* Reviewer time on this order — start, stop, and total, from the first
              review-open to when the sign-off/rejection output was generated. */}
          <div className="mt-3 border-t border-white/5 pt-3">
            <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              <Clock size={12} /> Reviewer time
            </div>
            {order.activeQcResult.reviewStartedAt ? (
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-[12px] sm:grid-cols-4">
                <div>
                  <div className="text-slate-600">Reviewer</div>
                  <div className="text-slate-300">{order.activeQcResult.reviewedBy ?? order.assignedReviewer?.fullName ?? order.assignedReviewer?.username ?? "—"}</div>
                </div>
                <div>
                  <div className="text-slate-600">Started</div>
                  <div className="tabular-nums text-slate-300">{formatDateTime(order.activeQcResult.reviewStartedAt)}</div>
                </div>
                <div>
                  <div className="text-slate-600">Finished</div>
                  <div className="tabular-nums text-slate-300">{order.activeQcResult.reviewedAt ? formatDateTime(order.activeQcResult.reviewedAt) : "In progress"}</div>
                </div>
                <div>
                  <div className="text-slate-600">Total time</div>
                  <div className="tabular-nums font-semibold text-slate-200">{formatDuration(order.activeQcResult.reviewDurationSeconds) ?? "—"}</div>
                </div>
              </div>
            ) : (
              <div className="text-[12px] text-slate-500">Not started yet — the reviewer hasn&apos;t opened this order.</div>
            )}
          </div>
        </div>
      )}

      {!loading && (
        <div className="mb-6">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <ClipboardList size={13} /> Order documents
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {([
              ["APPRAISAL", "Appraisal", true],
              ["APPRAISAL_XML", "Appraisal XML", true],
              ["ENGAGEMENT", "Engagement", true],
              ["CONTRACT", "Contract", false],
            ] as const).map(([type, label, required]) => {
              const doc = activeDocs.find(d => d.fileType === type);
              return (
                <div key={type} className={`rounded-lg border p-3 ${doc ? "border-green-500/20 bg-green-950/10" : required ? "border-amber-500/20 bg-amber-950/10" : "border-white/[0.06] bg-sunken/40"}`}>
                  <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
                    {doc ? <Check size={12} className="text-green-400" /> : <Minus size={12} className={required ? "text-amber-400" : "text-slate-600"} />}
                    <span>{label}{!required ? " · optional" : ""}</span>
                  </div>
                  <div className="mt-1 truncate text-[12px] text-slate-300" title={doc?.filename}>
                    {doc ? doc.filename
                      : required ? <span className="text-amber-300/80">Missing — assign from batch</span>
                      : <span className="text-slate-600">Not provided</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="mb-6">
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <FileText size={13} /> Active documents
        </div>
        {loading ? (
          <div className="rounded-xl border border-white/10 bg-surface p-4"><TableSkeleton rows={4} cols={4} /></div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-white/10 bg-surface">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/[0.06] text-left text-[11px] uppercase tracking-wide text-slate-600">
                  <th className="px-5 py-2.5 font-medium">File</th>
                  <th className="px-4 py-2.5 font-medium">Type</th>
                  <th className="px-4 py-2.5 font-medium">Version</th>
                  <th className="px-4 py-2.5 font-medium">From batch</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {activeDocs.length === 0 ? (
                  <tr><td colSpan={4} className="px-5 py-6 text-center text-sm text-slate-500">No active documents — this order is incomplete.</td></tr>
                ) : activeDocs.map(d => (
                  <tr key={d.id} className="hover:bg-white/[0.025]">
                    <td className="px-5 py-3 font-medium text-slate-200">{d.filename}</td>
                    <td className="px-4 py-3 text-slate-400">{fileTypeLabel(d.fileType)}</td>
                    <td className="px-4 py-3 tabular-nums text-slate-500">v{d.contentVersion}</td>
                    <td className="px-4 py-3">
                      {d.batchId && (
                        <Link href={`/admin/batches/${d.batchId}`} className="text-indigo-300 hover:text-indigo-200">
                          Batch #{d.batchId}
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {historicalDocs.length > 0 && (
        <div className="mb-6">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <History size={13} /> Superseded / duplicate documents ({historicalDocs.length})
          </div>
          <div className="overflow-hidden rounded-xl border border-white/10 bg-surface">
            <table className="w-full text-sm">
              <tbody className="divide-y divide-white/[0.04]">
                {historicalDocs.map(d => (
                  <tr key={d.id} className="text-slate-500">
                    <td className="px-5 py-2.5">{d.filename}</td>
                    <td className="px-4 py-2.5">{fileTypeLabel(d.fileType)}</td>
                    <td className="px-4 py-2.5 tabular-nums">v{d.contentVersion}</td>
                    <td className="px-4 py-2.5 text-[11px]">
                      {d.batchId && <Link href={`/admin/batches/${d.batchId}`} className="hover:text-slate-300">from batch #{d.batchId}</Link>}
                    </td>
                    <td className="px-4 py-2.5 text-[11px]">
                      {d.supersededAt ? `superseded ${new Date(d.supersededAt).toLocaleDateString("en-GB")}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div>
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <Package size={13} /> Seen in these batches ({order?.batchHistory.length ?? 0})
        </div>
        <p className="mb-2 text-[12px] text-slate-500">
          Every upload event that touched this order — re-uploads under a different ZIP folder name link here instead of forking a new order.
        </p>
        <div className="overflow-hidden rounded-xl border border-white/10 bg-surface divide-y divide-white/[0.04]">
          {(order?.batchHistory ?? []).map(b => (
            <Link key={b.id} href={`/admin/batches/${b.id}`} className="flex items-center justify-between px-5 py-3 text-sm transition-colors hover:bg-white/[0.025]">
              <span className="font-mono text-slate-200">{b.parentBatchId}</span>
              <div className="flex items-center gap-3">
                <StatusBadge status={b.status} size="xs" />
                <span className="text-[11px] text-slate-500">
                  {b.createdAt ? new Date(b.createdAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : ""}
                </span>
              </div>
            </Link>
          ))}
          {(order?.batchHistory ?? []).length === 0 && !loading && (
            <div className="px-5 py-6 text-center text-sm text-slate-500">No batch history found.</div>
          )}
        </div>
      </div>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={deleting ? undefined : () => setConfirmDelete(false)} />
          <div className="relative w-full max-w-md rounded-lg border border-red-500/25 bg-surface p-5 shadow-[0_22px_60px_rgba(0,0,0,0.46)]">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-red-200">
              <AlertTriangle size={16} className="text-red-400" /> Delete this order permanently?
            </div>
            <p className="text-[12px] leading-relaxed text-slate-400">
              <span className="font-mono text-slate-200">{order?.transactionRef}</span> and its{" "}
              <strong className="text-slate-200">{activeDocs.length + historicalDocs.length} document(s)</strong>{" "}
              (appraisal, XML, engagement, contract) will be permanently removed from the database and disk.
              This cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setConfirmDelete(false)} disabled={deleting}
                className="rounded-md border border-white/10 bg-muted px-4 py-2 text-sm text-slate-300 transition-colors hover:bg-white/[0.04] hover:text-white disabled:opacity-40">
                Cancel
              </button>
              <button onClick={handleDelete} disabled={deleting}
                className="inline-flex items-center gap-1.5 rounded-md border border-red-500/40 bg-red-600/80 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-600 disabled:opacity-50">
                <Trash2 size={13} /> {deleting ? "Deleting…" : "Delete permanently"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

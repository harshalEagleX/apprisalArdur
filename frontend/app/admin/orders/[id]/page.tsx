"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, ChevronRight, ClipboardList, FileText, Package,
  RefreshCw, History, Play, UserPlus,
} from "lucide-react";
import {
  getOrderById, getAllUsers, processOrderQC, assignOrderReviewer,
  type OrderDetail, type User,
} from "@/lib/api";
import { Skeleton, TableSkeleton } from "@/components/shared/Skeleton";
import StatusBadge from "@/components/shared/StatusBadge";
import { toast } from "@/lib/toast";

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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setOrder(await getOrderById(id));
    } catch {
      toast.error("Failed to load order");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    getAllUsers().then(list => setReviewers(list.filter(u => u.role === "REVIEWER"))).catch(() => undefined);
  }, []);

  async function handleRunQC() {
    setActionRunning(true);
    try {
      const res = await processOrderQC(id);
      if ((res.startedBatchIds?.length ?? 0) > 0) toast.success("QC started for this order.");
      else toast.info("Nothing started", res.message || "Order may already be processing.");
      void load();
    } catch (e) {
      toast.error("Failed to start QC", String(e));
    } finally {
      setActionRunning(false);
    }
  }

  async function handleAssign(value: string) {
    const reviewerId = value ? Number(value) : null;
    setActionRunning(true);
    try {
      await assignOrderReviewer(id, reviewerId);
      toast.success(reviewerId ? "Reviewer assigned." : "Reviewer cleared.");
      void load();
    } catch (e) {
      toast.error("Assignment failed", String(e));
    } finally {
      setActionRunning(false);
    }
  }

  const activeDocs = order?.documents.filter(d => d.active) ?? [];
  const historicalDocs = order?.documents.filter(d => !d.active) ?? [];

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
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-[#161B22]">
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
          <button onClick={handleRunQC} disabled={actionRunning}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-indigo-500/40 bg-indigo-500/10 px-3 text-xs text-indigo-200 transition-colors hover:bg-indigo-500/20 disabled:opacity-40">
            <Play size={12} /> Run QC
          </button>
          <div className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-[#11161C] px-2">
            <UserPlus size={12} className="text-slate-500" />
            <select
              value={order?.assignedReviewer?.id ?? ""}
              onChange={e => handleAssign(e.target.value)}
              disabled={actionRunning}
              aria-label="Assign reviewer"
              className="h-8 bg-transparent pr-1 text-xs text-slate-300 focus:outline-none disabled:opacity-40"
            >
              <option value="">Unassigned</option>
              {reviewers.map(r => <option key={r.id} value={r.id}>{r.fullName || r.username}</option>)}
            </select>
          </div>
          <button onClick={() => load()} className="flex h-8 items-center gap-1.5 rounded-md border border-white/10 bg-[#11161C] px-3 text-xs text-slate-400 transition-colors hover:text-white">
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </header>

      {order?.activeQcResult && (
        <div className="mb-6 rounded-xl border border-white/10 bg-[#11161C] p-4">
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
        </div>
      )}

      <div className="mb-6">
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <FileText size={13} /> Active documents
        </div>
        {loading ? (
          <div className="rounded-xl border border-white/10 bg-[#11161C] p-4"><TableSkeleton rows={4} cols={4} /></div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-white/10 bg-[#11161C]">
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
          <div className="overflow-hidden rounded-xl border border-white/10 bg-[#11161C]">
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
        <div className="overflow-hidden rounded-xl border border-white/10 bg-[#11161C] divide-y divide-white/[0.04]">
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
    </div>
  );
}

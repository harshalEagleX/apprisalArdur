"use client";
import { useEffect, useState, useCallback } from "react";
import { getAdminBatches, getUsers, processQC, assignReviewer, deleteBatch, getBatchStatus, type Batch, type User } from "@/lib/api";
import StatusBadge from "@/components/shared/StatusBadge";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import UploadModal from "@/components/admin/UploadModal";

const STATUSES = ["", "UPLOADED", "VALIDATING", "QC_PROCESSING", "REVIEW_PENDING", "IN_REVIEW", "COMPLETED", "ERROR"];

export default function BatchesPage() {
  const [batches, setBatches]     = useState<Batch[]>([]);
  const [reviewers, setReviewers] = useState<User[]>([]);
  const [page, setPage]           = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [statusFilter, setStatus] = useState("");
  const [loading, setLoading]     = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Batch | null>(null);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

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
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => { load(); }, [load]);

  async function handleProcessQC(batchId: number) {
    setActionLoading(batchId);
    try {
      const res = await processQC(batchId);
      // 202 Accepted — poll until status changes from QC_PROCESSING
      if (res.pollUrl) {
        await pollUntilDone(batchId);
      }
      await load();
    } catch (e) {
      alert("QC trigger failed: " + String(e));
    } finally {
      setActionLoading(null);
    }
  }

  async function pollUntilDone(batchId: number, maxAttempts = 60) {
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(r => setTimeout(r, 5000));
      try {
        const status = await getBatchStatus(batchId);
        if (status.status !== "QC_PROCESSING") return;
      } catch { return; }
    }
  }

  async function handleAssign(batchId: number, reviewerId: number) {
    setActionLoading(batchId);
    try { await assignReviewer(batchId, reviewerId); await load(); }
    catch (e) { alert("Assign failed: " + String(e)); }
    finally { setActionLoading(null); }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try { await deleteBatch(deleteTarget.id); setDeleteTarget(null); await load(); }
    catch (e) { alert("Delete failed: " + String(e)); }
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">Batch Management</h1>
        <button onClick={() => setShowUpload(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg font-medium transition-colors">
          + Upload Batch
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-4">
        <select value={statusFilter} onChange={e => { setStatus(e.target.value); setPage(0); }}
          className="bg-slate-900 border border-slate-700 text-slate-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500">
          <option value="">All statuses</option>
          {STATUSES.filter(Boolean).map(s => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
        </select>
      </div>

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-slate-800 text-slate-400 text-xs uppercase">
            <tr>
              {["Batch ID", "Client", "Status", "Files", "Reviewer", "Date", "Actions"].map(h => (
                <th key={h} className="px-4 py-3 text-left whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {loading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">Loading…</td></tr>
            ) : batches.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">No batches found</td></tr>
            ) : batches.map(b => (
              <tr key={b.id} className="hover:bg-slate-800/30">
                <td className="px-4 py-3">
                  <div className="font-mono text-xs text-slate-300 max-w-[160px] truncate" title={b.parentBatchId}>
                    {b.parentBatchId}
                  </div>
                </td>
                <td className="px-4 py-3 text-slate-300 text-xs">{b.client?.name ?? "—"}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={b.status} />
                  {b.errorMessage && (b.status === "ERROR" || b.status === "VALIDATION_FAILED") && (
                    <div className="text-red-400 text-[10px] mt-0.5 max-w-[160px] truncate" title={b.errorMessage}>
                      {b.errorMessage}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3 text-slate-400 text-xs">{b.files?.length ?? 0}</td>
                <td className="px-4 py-3 text-slate-400 text-xs">
                  {b.assignedReviewer ? (b.assignedReviewer.fullName ?? b.assignedReviewer.username) : (
                    <span className="text-slate-600">Unassigned</span>
                  )}
                </td>
                <td className="px-4 py-3 text-slate-500 text-xs">
                  {new Date(b.createdAt).toLocaleDateString()}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    {/* Run QC */}
                    {(b.status === "UPLOADED" || b.status === "VALIDATING" || b.status === "ERROR") && (
                      <button
                        onClick={() => handleProcessQC(b.id)}
                        disabled={actionLoading === b.id}
                        className="bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 text-white text-xs px-2 py-1 rounded font-medium transition-colors flex items-center gap-1"
                      >
                        {actionLoading === b.id && (
                          <span className="inline-block animate-spin h-2.5 w-2.5 border border-white border-t-transparent rounded-full" />
                        )}
                        {actionLoading === b.id ? "Processing…" : b.status === "ERROR" ? "Retry QC" : "Run QC"}
                      </button>
                    )}
                    {b.status === "QC_PROCESSING" && (
                      <span className="text-indigo-400 text-xs flex items-center gap-1">
                        <span className="inline-block animate-spin h-2.5 w-2.5 border border-indigo-400 border-t-transparent rounded-full" />
                        Processing…
                      </span>
                    )}

                    {/* Assign reviewer */}
                    {(b.status === "REVIEW_PENDING" || b.status === "QC_PROCESSING") && reviewers.length > 0 && (
                      <select
                        defaultValue=""
                        onChange={e => e.target.value && handleAssign(b.id, Number(e.target.value))}
                        disabled={actionLoading === b.id}
                        className="bg-slate-800 text-slate-300 text-xs px-2 py-1 rounded border border-slate-700 focus:outline-none"
                      >
                        <option value="">Assign…</option>
                        {reviewers.map(r => (
                          <option key={r.id} value={r.id}>
                            {r.fullName ?? r.username}
                          </option>
                        ))}
                      </select>
                    )}

                    {/* Delete */}
                    <button
                      onClick={() => setDeleteTarget(b)}
                      className="text-red-400 hover:text-red-300 text-xs px-2 py-1 rounded hover:bg-red-900/20 transition-colors"
                    >
                      Del
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
            className="text-slate-400 disabled:opacity-30 hover:text-white text-sm px-3 py-1.5 rounded-lg hover:bg-slate-800 transition-colors">
            ← Previous
          </button>
          <span className="text-slate-500 text-sm">Page {page + 1} of {totalPages}</span>
          <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
            className="text-slate-400 disabled:opacity-30 hover:text-white text-sm px-3 py-1.5 rounded-lg hover:bg-slate-800 transition-colors">
            Next →
          </button>
        </div>
      )}

      {/* Modals */}
      <UploadModal
        open={showUpload}
        onClose={() => setShowUpload(false)}
        onUploaded={() => load()}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Batch"
        message={`Delete "${deleteTarget?.parentBatchId}"? All associated files and QC results will be permanently removed.`}
        confirmLabel="Delete"
        danger
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

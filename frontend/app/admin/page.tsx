"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getAdminDashboard, type Batch, type User } from "@/lib/api";
import StatCard from "@/components/shared/StatCard";
import StatusBadge from "@/components/shared/StatusBadge";

export default function AdminOverviewPage() {
  const [dash, setDash]   = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAdminDashboard()
      .then(setDash)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const n = (k: string) => Number(dash[k] ?? 0);
  const recentBatches = (dash.recentBatches as Batch[] | undefined) ?? [];
  const reviewers     = (dash.reviewers as User[] | undefined) ?? [];
  const workload      = (dash.reviewerWorkload as Record<string, number> | undefined) ?? {};

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">Overview</h1>
        <Link href="/admin/batches"
          className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg font-medium transition-colors">
          Upload Batch
        </Link>
      </div>

      {loading ? (
        <div className="text-slate-500 text-sm">Loading…</div>
      ) : (
        <>
          {/* Metrics grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 mb-8">
            <StatCard label="Total Batches"  value={n("totalBatches")}  color="text-slate-200" />
            <StatCard label="QC Processing"  value={n("pendingOcr")}    color="text-indigo-400" />
            <StatCard label="Pending Review" value={n("pendingReview")} color="text-amber-400" />
            <StatCard label="In Review"      value={n("inReview")}      color="text-orange-400" />
            <StatCard label="Completed"      value={n("completed")}     color="text-green-400" />
            <StatCard label="Errors"         value={n("errors")}        color="text-red-400" />
            <StatCard label="Reviewers"      value={n("reviewerCount")} color="text-blue-400" />
            <StatCard label="Client Orgs"    value={n("clientOrganizations")} color="text-purple-400" />
          </div>

          {/* Two columns: recent batches + reviewer workload */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* Recent batches */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
                <h2 className="text-sm font-semibold text-slate-200">Recent Batches</h2>
                <Link href="/admin/batches" className="text-xs text-blue-400 hover:underline">View all →</Link>
              </div>
              {recentBatches.length === 0 ? (
                <div className="px-4 py-8 text-center text-slate-500 text-sm">No batches yet</div>
              ) : (
                <table className="w-full text-sm">
                  <tbody className="divide-y divide-slate-800">
                    {recentBatches.slice(0, 6).map(b => (
                      <tr key={b.id} className="hover:bg-slate-800/40">
                        <td className="px-4 py-2.5">
                          <div className="font-mono text-xs text-slate-300 truncate max-w-[180px]">{b.parentBatchId}</div>
                          <div className="text-slate-500 text-[11px]">{b.client?.name ?? "—"}</div>
                        </td>
                        <td className="px-4 py-2.5">
                          <StatusBadge status={b.status} />
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-500 text-xs">
                          {new Date(b.createdAt).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Reviewer workload */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
                <h2 className="text-sm font-semibold text-slate-200">Reviewer Workload</h2>
                <Link href="/admin/users" className="text-xs text-blue-400 hover:underline">Manage →</Link>
              </div>
              {reviewers.length === 0 ? (
                <div className="px-4 py-8 text-center text-slate-500 text-sm">
                  No reviewers yet.{" "}
                  <Link href="/admin/users" className="text-blue-400 hover:underline">Add one →</Link>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="border-b border-slate-800 text-slate-500 text-xs">
                    <tr>
                      <th className="px-4 py-2 text-left">Reviewer</th>
                      <th className="px-4 py-2 text-right">Active</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {reviewers.map(r => (
                      <tr key={r.id} className="hover:bg-slate-800/40">
                        <td className="px-4 py-2.5">
                          <div className="text-slate-200">{r.fullName ?? r.username}</div>
                          <div className="text-slate-500 text-xs">{r.username}</div>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <span className={`font-bold ${workload[r.id] > 0 ? "text-amber-400" : "text-slate-500"}`}>
                            {workload[r.id] ?? 0}
                          </span>
                          <span className="text-slate-600 text-xs ml-1">batches</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

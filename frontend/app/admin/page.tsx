"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Package, Users, AlertCircle, CheckCircle2, Clock, Loader, Building2, ArrowRight } from "lucide-react";
import { getAdminDashboard, type Batch, type User } from "@/lib/api";
import StatCard from "@/components/shared/StatCard";
import StatusBadge from "@/components/shared/StatusBadge";
import { CardSkeleton, Skeleton } from "@/components/shared/Skeleton";

export default function AdminOverviewPage() {
  const [dash, setDash]   = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAdminDashboard().then(setDash).catch(console.error).finally(() => setLoading(false));
  }, []);

  const n = (k: string) => Number(dash[k] ?? 0);
  const recentBatches = (dash.recentBatches as Batch[] | undefined) ?? [];
  const reviewers     = (dash.reviewers     as User[]  | undefined) ?? [];
  const workload      = (dash.reviewerWorkload as Record<string, number> | undefined) ?? {};

  return (
    <div className="p-6 max-w-6xl">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-white">Overview</h1>
        <p className="text-slate-500 text-sm mt-0.5">Platform status at a glance</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
        {loading ? (
          Array.from({ length: 8 }).map((_, i) => <CardSkeleton key={i} />)
        ) : (
          <>
            <StatCard label="Total batches"    value={n("totalBatches")}   icon={Package}      color="slate" />
            <StatCard label="QC running"       value={n("pendingOcr")}     icon={Loader}       color="indigo" />
            <StatCard label="Awaiting review"  value={n("pendingReview")}  icon={Clock}        color="amber" />
            <StatCard label="In review"        value={n("inReview")}       icon={Clock}        color="amber" />
            <StatCard label="Completed"        value={n("completed")}      icon={CheckCircle2} color="green" />
            <StatCard label="Errors"           value={n("errors")}         icon={AlertCircle}  color="red" />
            <StatCard label="Active reviewers" value={n("reviewerCount")}  icon={Users}        color="blue" />
            <StatCard label="Client orgs"      value={n("clientOrganizations")} icon={Building2} color="slate" />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Recent batches */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800">
            <span className="text-sm font-medium text-slate-200">Recent batches</span>
            <Link href="/admin/batches" className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors">
              View all <ArrowRight size={12} />
            </Link>
          </div>
          {loading ? (
            <div className="divide-y divide-slate-800">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center justify-between px-5 py-3 gap-3">
                  <Skeleton className="h-3.5 w-40" />
                  <Skeleton className="h-5 w-20 rounded-full" />
                  <Skeleton className="h-3 w-16" />
                </div>
              ))}
            </div>
          ) : recentBatches.length === 0 ? (
            <div className="px-5 py-10 text-center text-slate-500 text-sm">No batches yet</div>
          ) : (
            <div className="divide-y divide-slate-800">
              {recentBatches.slice(0, 6).map(b => (
                <div key={b.id} className="flex items-center gap-3 px-5 py-3 hover:bg-slate-800/40 transition-colors">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-mono text-slate-300 truncate">{b.parentBatchId}</div>
                    <div className="text-[11px] text-slate-500 mt-0.5">{b.client?.name ?? "—"}</div>
                  </div>
                  <StatusBadge status={b.status} />
                  <div className="text-[11px] text-slate-600 flex-shrink-0">
                    {new Date(b.createdAt).toLocaleDateString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Reviewer workload */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800">
            <span className="text-sm font-medium text-slate-200">Reviewer workload</span>
            <Link href="/admin/users" className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors">
              Manage <ArrowRight size={12} />
            </Link>
          </div>
          {loading ? (
            <div className="divide-y divide-slate-800">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex items-center px-5 py-3 gap-3">
                  <Skeleton className="h-3.5 flex-1" />
                  <Skeleton className="h-3.5 w-12" />
                </div>
              ))}
            </div>
          ) : reviewers.length === 0 ? (
            <div className="px-5 py-10 text-center">
              <p className="text-slate-500 text-sm mb-3">No reviewers yet</p>
              <Link href="/admin/users" className="text-xs text-blue-400 hover:underline">Add a reviewer</Link>
            </div>
          ) : (
            <div className="divide-y divide-slate-800">
              {reviewers.map(r => {
                const active = workload[r.id] ?? 0;
                return (
                  <div key={r.id} className="flex items-center gap-3 px-5 py-3">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-slate-200 truncate">{r.fullName ?? r.username}</div>
                      <div className="text-[11px] text-slate-500">{r.username}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* Workload bar */}
                      <div className="w-20 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${Math.min(active * 20, 100)}%`,
                            background: active > 3 ? "#f59e0b" : "#3b82f6",
                          }}
                        />
                      </div>
                      <span className={`text-xs font-mono font-semibold tabular-nums ${active > 0 ? "text-slate-300" : "text-slate-600"}`}>
                        {active}
                      </span>
                      <span className="text-[11px] text-slate-600">active</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

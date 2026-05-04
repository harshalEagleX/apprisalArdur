"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Package, Users, AlertCircle, CheckCircle2, Clock, Loader, Building2,
  ArrowRight, Upload, UserPlus, Activity, ShieldAlert, CalendarDays,
} from "lucide-react";
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
  const alerts = [
    {
      key: "errors",
      count: n("errors"),
      title: "Fix failed batches",
      detail: "Retry QC or delete/re-upload batches that ended in error.",
      href: "/admin/batches?status=ERROR",
      tone: "red" as const,
      icon: ShieldAlert,
    },
    {
      key: "review",
      count: n("pendingReview"),
      title: "Assign review work",
      detail: "Batches are ready for reviewers and should not sit unassigned.",
      href: "/admin/batches?status=REVIEW_PENDING",
      tone: "amber" as const,
      icon: UserPlus,
    },
    {
      key: "qc",
      count: n("pendingOcr"),
      title: "Monitor QC processing",
      detail: "OCR/rule validation is running. Watch for stalled work.",
      href: "/admin/batches?status=QC_PROCESSING",
      tone: "indigo" as const,
      icon: Loader,
    },
  ].filter(item => item.count > 0);
  const nextAction = alerts[0] ?? {
    key: "healthy",
    count: n("completed"),
    title: "System is clear",
    detail: recentBatches.length > 0 ? "No urgent batch action is needed right now." : "Upload a batch to begin the first QC workflow.",
    href: recentBatches.length > 0 ? "/admin/batches" : "/admin/batches",
    tone: "green" as const,
    icon: CheckCircle2,
  };
  const workflow = [
    { label: "QC running", value: n("pendingOcr"), href: "/admin/batches?status=QC_PROCESSING", tone: "indigo" as const },
    { label: "Awaiting review", value: n("pendingReview"), href: "/admin/batches?status=REVIEW_PENDING", tone: "amber" as const },
    { label: "In review", value: n("inReview"), href: "/admin/batches?status=IN_REVIEW", tone: "blue" as const },
    { label: "Completed", value: n("completed"), href: "/admin/batches?status=COMPLETED", tone: "green" as const },
    { label: "Errors", value: n("errors"), href: "/admin/batches?status=ERROR", tone: "red" as const },
  ];
  const todayKey = new Date().toDateString();
  const createdToday = recentBatches.filter(batch => new Date(batch.createdAt).toDateString() === todayKey).length;
  const latestActivity = recentBatches
    .map(batch => batch.updatedAt ?? batch.createdAt)
    .filter(Boolean)
    .sort((a, b) => new Date(b).getTime() - new Date(a).getTime())[0];
  const latestActivityLabel = latestActivity
    ? new Date(latestActivity).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    : "No activity yet";

  return (
    <div className="p-6 max-w-[1400px]">
      <div className="mb-5 flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Overview</h1>
          <p className="text-slate-500 text-sm mt-0.5">Operational home for QC intake, processing, assignment, and review follow-up</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/admin/batches" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white transition-colors hover:bg-blue-700">
            <Upload size={14} /> Upload or run QC
          </Link>
          <Link href="/admin/users" className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 text-sm text-slate-300 transition-colors hover:bg-slate-800">
            <Users size={14} /> Manage reviewers
          </Link>
        </div>
      </div>

      {loading ? (
        <div className="mb-5 grid gap-3 lg:grid-cols-[1.2fr_1fr]">
          <CardSkeleton />
          <CardSkeleton />
        </div>
      ) : (
        <div className="mb-5 grid gap-3 lg:grid-cols-[1.2fr_1fr]">
          <NextActionPanel action={nextAction} />
          <SystemSignal
            totalBatches={n("totalBatches")}
            createdToday={createdToday}
            latestActivity={latestActivityLabel}
            clients={n("clientOrganizations")}
          />
        </div>
      )}

      {/* Decision metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-3 mb-5">
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

      <div className="mb-5 rounded-lg border border-slate-800 bg-slate-900 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">Workflow visibility</h2>
            <p className="mt-0.5 text-[11px] text-slate-500">Jump directly into the stage that needs attention.</p>
          </div>
          <Link href="/admin/batches" className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300">
            All batches <ArrowRight size={12} />
          </Link>
        </div>
        {loading ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          <div className="grid gap-2 md:grid-cols-5">
            {workflow.map(stage => <WorkflowStage key={stage.label} {...stage} />)}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-5">
        <div className="space-y-5">
          <AttentionList loading={loading} alerts={alerts} />
          <RecentActivity loading={loading} recentBatches={recentBatches} />
        </div>

        {/* Reviewer workload */}
        <div className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800">
            <div>
              <span className="text-sm font-medium text-slate-200">Reviewer workload</span>
              <p className="mt-0.5 text-[11px] text-slate-500">Prioritize assignments by active load.</p>
            </div>
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
              {reviewers
                .map(reviewer => ({ reviewer, active: workload[reviewer.id] ?? 0 }))
                .sort((a, b) => b.active - a.active)
                .map(({ reviewer: r, active }) => (
                <div key={r.id} className="flex items-center gap-3 px-5 py-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-slate-200 truncate">{r.fullName ?? r.username}</div>
                    <div className="text-[11px] text-slate-500">{r.username}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-1.5 bg-slate-800 rounded-full overflow-hidden">
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
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function NextActionPanel({ action }: { action: {
  count: number;
  title: string;
  detail: string;
  href: string;
  tone: "red" | "amber" | "indigo" | "green";
  icon: React.ComponentType<{ size?: number; className?: string }>;
} }) {
  const Icon = action.icon;
  const tone = {
    red: "border-red-900/50 bg-red-950/25 text-red-200",
    amber: "border-amber-900/50 bg-amber-950/25 text-amber-200",
    indigo: "border-indigo-900/50 bg-indigo-950/25 text-indigo-200",
    green: "border-green-900/50 bg-green-950/25 text-green-200",
  }[action.tone];
  return (
    <Link href={action.href} className={`group flex min-h-32 items-center gap-4 rounded-lg border p-4 transition-colors hover:border-blue-700/60 ${tone}`}>
      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-current/20 bg-slate-950/30">
        <Icon size={22} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-semibold uppercase tracking-wide opacity-70">Next best action</div>
        <div className="mt-1 text-lg font-semibold text-white">{action.title}</div>
        <div className="mt-1 text-sm leading-relaxed opacity-80">{action.detail}</div>
      </div>
      <div className="flex items-center gap-2 text-sm font-semibold text-white">
        <span className="font-mono tabular-nums">{action.count}</span>
        <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
      </div>
    </Link>
  );
}

function SystemSignal({ totalBatches, createdToday, latestActivity, clients }: {
  totalBatches: number;
  createdToday: number;
  latestActivity: string;
  clients: number;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
        <Activity size={15} className="text-blue-400" />
        System signals
      </div>
      <div className="grid grid-cols-2 gap-2">
        <MiniSignal label="Batches" value={totalBatches} />
        <MiniSignal label="New today" value={createdToday} />
        <MiniSignal label="Clients" value={clients} />
        <MiniSignal label="Latest activity" value={latestActivity} icon={CalendarDays} />
      </div>
    </div>
  );
}

function MiniSignal({ label, value, icon: Icon }: { label: string; value: number | string; icon?: React.ComponentType<{ size?: number; className?: string }> }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2">
      <div className="flex items-center gap-1.5 text-base font-semibold text-slate-100 tabular-nums">
        {Icon && <Icon size={13} className="text-slate-500" />}
        <span className="truncate">{value}</span>
      </div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}

function WorkflowStage({ label, value, href, tone }: {
  label: string;
  value: number;
  href: string;
  tone: "indigo" | "amber" | "blue" | "green" | "red";
}) {
  const styles = {
    indigo: "hover:border-indigo-700 text-indigo-200",
    amber: "hover:border-amber-700 text-amber-200",
    blue: "hover:border-blue-700 text-blue-200",
    green: "hover:border-green-700 text-green-200",
    red: "hover:border-red-700 text-red-200",
  };
  return (
    <Link href={href} className={`rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-3 transition-colors ${styles[tone]}`}>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
    </Link>
  );
}

function AttentionList({ loading, alerts }: { loading: boolean; alerts: Array<{
  key: string;
  count: number;
  title: string;
  detail: string;
  href: string;
  tone: "red" | "amber" | "indigo";
  icon: React.ComponentType<{ size?: number; className?: string }>;
}> }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800">
        <div>
          <span className="text-sm font-medium text-slate-200">Attention areas</span>
          <p className="mt-0.5 text-[11px] text-slate-500">Urgent work is sorted first.</p>
        </div>
      </div>
      {loading ? (
        <div className="space-y-3 p-5">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : alerts.length === 0 ? (
        <div className="px-5 py-8 text-center">
          <CheckCircle2 size={20} className="mx-auto mb-2 text-green-400" />
          <p className="text-sm font-medium text-slate-300">No urgent admin action</p>
          <p className="mt-1 text-xs text-slate-500">Processing, review, and error queues are clear.</p>
        </div>
      ) : (
        <div className="divide-y divide-slate-800">
          {alerts.map(alert => {
            const Icon = alert.icon;
            return (
              <Link key={alert.key} href={alert.href} className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-slate-800/40">
                <Icon size={16} className={alert.tone === "red" ? "text-red-300" : alert.tone === "amber" ? "text-amber-300" : "text-indigo-300"} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-slate-200">{alert.title}</div>
                  <div className="mt-0.5 truncate text-[11px] text-slate-500">{alert.detail}</div>
                </div>
                <div className="font-mono text-sm font-semibold text-slate-200 tabular-nums">{alert.count}</div>
                <ArrowRight size={13} className="text-slate-600" />
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

function RecentActivity({ loading, recentBatches }: { loading: boolean; recentBatches: Batch[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800">
        <div>
          <span className="text-sm font-medium text-slate-200">Recent activity</span>
          <p className="mt-0.5 text-[11px] text-slate-500">Resume recent batches or verify the last system output.</p>
        </div>
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
        <div className="px-5 py-10 text-center">
          <Package size={20} className="mx-auto mb-2 text-slate-600" />
          <p className="text-sm font-medium text-slate-300">No batches yet</p>
          <p className="mt-1 text-xs text-slate-500">Upload the first ZIP archive to start the workflow.</p>
          <Link href="/admin/batches" className="mt-3 inline-flex items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300">
            Upload first batch <ArrowRight size={13} />
          </Link>
        </div>
      ) : (
        <div className="divide-y divide-slate-800">
          {recentBatches.slice(0, 6).map(b => (
            <Link key={b.id} href="/admin/batches" className="flex items-center gap-3 px-5 py-3 hover:bg-slate-800/40 transition-colors">
              <div className="flex-1 min-w-0">
                <div className="text-xs font-mono text-slate-300 truncate">{b.parentBatchId}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">{b.client?.name ?? "—"}</div>
              </div>
              <StatusBadge status={b.status} />
              <div className="text-[11px] text-slate-600 flex-shrink-0">
                {new Date(b.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

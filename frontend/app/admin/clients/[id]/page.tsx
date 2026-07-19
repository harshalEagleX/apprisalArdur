"use client";
import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Building2, Package, Users as UsersIcon, ChevronRight } from "lucide-react";
import { getClientDetail, type ClientDetail } from "@/lib/api";
import { TableSkeleton } from "@/components/shared/Skeleton";
import EmptyState from "@/components/shared/EmptyState";
import { toast } from "@/lib/toast";

export default function ClientDetailPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [data, setData] = useState<ClientDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await getClientDetail(id)); }
    catch { toast.error("Failed to load client"); }
    finally { setLoading(false); }
  }, [id]);

  useEffect(() => { const t = window.setTimeout(() => { void load(); }, 0); return () => window.clearTimeout(t); }, [load]);

  const c = data?.client;
  const s = data?.stats;

  return (
    <div className="w-full max-w-[1800px] p-6">
      {/* Breadcrumb */}
      <nav className="mb-3 flex items-center gap-1.5 text-xs text-slate-500">
        <Link href="/admin/clients" className="inline-flex items-center gap-1 transition-colors hover:text-slate-300">
          <ArrowLeft size={12} /> Clients
        </Link>
        <ChevronRight size={12} className="text-slate-600" />
        <span className="text-slate-300">{c?.name ?? "Client"}</span>
      </nav>

      <div className="mb-5 flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-lg border border-white/10 bg-muted text-lg font-bold text-slate-300">
          {c?.name ? c.name[0].toUpperCase() : <Building2 size={18} />}
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-normal text-white">{c?.name ?? "—"}</h1>
          <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
            <span className="font-mono">{c?.code ?? "—"}</span>
            {c?.status && (
              <span className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 ${c.status === "ACTIVE" ? "border-green-500/25 bg-green-950/40 text-green-200" : "border-white/10 bg-muted text-slate-500"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${c.status === "ACTIVE" ? "bg-green-400" : "bg-slate-500"}`} />{c.status}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Batches" value={s?.batches ?? 0} />
        <Stat label="Completed" value={s?.completed ?? 0} tone="text-green-300" />
        <Stat label="Success rate" value={s?.successRate != null ? `${s.successRate}%` : "—"}
          tone={s?.successRate != null && s.successRate >= 80 ? "text-green-300" : s?.successRate != null && s.successRate >= 50 ? "text-amber-300" : "text-slate-200"} />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Recent batches */}
        <section className="overflow-hidden rounded-lg border border-white/10 bg-surface">
          <h2 className="flex items-center gap-2 border-b border-white/10 px-4 py-3 text-sm font-semibold text-slate-200">
            <Package size={14} className="text-slate-500" /> Recent batches
          </h2>
          {loading ? <TableSkeleton rows={4} cols={3} /> : !data?.recentBatches.length ? (
            <EmptyState icon={Package} title="No batches yet" description="Batches uploaded for this client will appear here." />
          ) : (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-white/5">
                {data.recentBatches.map(b => (
                  <tr key={b.id} className="transition-colors hover:bg-white/[0.03]">
                    <td className="px-4 py-2.5">
                      <Link href={`/admin/batches/${b.id}`} className="font-medium text-slate-200 hover:text-white hover:underline">{b.parentBatchId ?? `Batch #${b.id}`}</Link>
                      <div className="text-[11px] text-slate-500">{b.fileCount} file{b.fileCount === 1 ? "" : "s"}</div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-400">{b.status?.replace(/_/g, " ")}</td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-500">
                      {b.createdAt ? new Date(b.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* Users */}
        <section className="overflow-hidden rounded-lg border border-white/10 bg-surface">
          <h2 className="flex items-center gap-2 border-b border-white/10 px-4 py-3 text-sm font-semibold text-slate-200">
            <UsersIcon size={14} className="text-slate-500" /> Users
          </h2>
          {loading ? <TableSkeleton rows={4} cols={2} /> : !data?.users.length ? (
            <EmptyState icon={UsersIcon} title="No users" description="Users assigned to this client will appear here." />
          ) : (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-white/5">
                {data.users.map(u => (
                  <tr key={u.id} className="transition-colors hover:bg-white/[0.03]">
                    <td className="px-4 py-2.5">
                      <div className="font-medium text-slate-200">{u.fullName ?? u.username}</div>
                      <div className="text-[11px] text-slate-500">{u.username}</div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-400">{u.role === "ADMIN" ? "Admin" : "Reviewer"}</td>
                    <td className="px-4 py-2.5 text-right text-[11px]">
                      {u.active
                        ? <span className="text-green-300">Active</span>
                        : <span className="text-slate-500">Inactive</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}

function Stat({ label, value, tone = "text-white" }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-surface p-4">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${tone}`}>{value}</div>
    </div>
  );
}

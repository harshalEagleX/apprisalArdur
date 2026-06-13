"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Search, Timer, ChevronLeft, ChevronRight, Layers, Gauge, FileSearch, ArrowRight,
} from "lucide-react";
import { getDocStats, type DocStatSummary } from "@/lib/api";
import { fmtMs, durationTone } from "@/lib/duration";
import { TableSkeleton } from "@/components/shared/Skeleton";
import EmptyState from "@/components/shared/EmptyState";
import StatusBadge from "@/components/shared/StatusBadge";
import { toast } from "@/lib/toast";

export default function DocStatsPage() {
  const [rows, setRows]       = useState<DocStatSummary[]>([]);
  const [page, setPage]       = useState(0);
  const [total, setTotal]     = useState(1);
  const [count, setCount]     = useState(0);
  const [search, setSearch]   = useState("");
  const [query, setQuery]     = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getDocStats(page, query || undefined);
      setRows(res.content);
      setTotal(Math.max(1, res.totalPages));
      setCount(res.totalElements);
    } catch {
      toast.error("Failed to load docStats");
    } finally {
      setLoading(false);
    }
  }, [page, query]);

  useEffect(() => {
    const t = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(t);
  }, [load]);

  // debounce the search box → server query
  useEffect(() => {
    const t = window.setTimeout(() => { setPage(0); setQuery(search); }, 300);
    return () => window.clearTimeout(t);
  }, [search]);

  const onPage = rows.length;

  return (
    <div className="p-6 lg:p-8 max-w-[1400px] mx-auto">
      {/* Header */}
      <header className="mb-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-indigo-500/25 bg-indigo-600/15">
            <Timer size={18} className="text-indigo-300" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-white">DocStats — QC timing</h1>
            <p className="text-xs text-slate-500">
              Real measured time each pipeline stage and QC rule took, per appraisal. Pulled from the engine&apos;s own clock.
            </p>
          </div>
        </div>
      </header>

      {/* Search */}
      <div className="mb-4 flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by appraisal filename, client, or batch id…"
            className="h-10 w-full rounded-lg border border-white/10 bg-[#11161C] pl-9 pr-3 text-sm text-white placeholder:text-slate-600 focus:border-indigo-500/40 focus:outline-none"
          />
        </div>
        <span className="text-xs text-slate-500 tabular-nums">{count} appraisal{count === 1 ? "" : "s"} measured</span>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-white/10 bg-[#11161C]/60">
        {loading ? (
          <div className="p-4"><TableSkeleton rows={8} /></div>
        ) : onPage === 0 ? (
          <EmptyState
            icon={FileSearch}
            title={query ? "No matching appraisals" : "No QC timings yet"}
            description={query
              ? "Try a different filename, client, or batch id."
              : "Run QC on a batch — timings are captured automatically for every appraisal."}
          />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-[11px] uppercase tracking-wide text-slate-500">
                <th className="px-4 py-2.5 font-medium">Appraisal</th>
                <th className="px-4 py-2.5 font-medium">Decision</th>
                <th className="px-4 py-2.5 font-medium text-right">Total</th>
                <th className="px-4 py-2.5 font-medium text-right">Rule engine</th>
                <th className="px-4 py-2.5 font-medium text-right">Rules</th>
                <th className="px-4 py-2.5 font-medium">Slowest stage</th>
                <th className="px-4 py-2.5 font-medium">Slowest rule</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id} className="group border-b border-white/[0.04] transition-colors hover:bg-white/[0.03]">
                  <td className="px-4 py-3">
                    <Link href={`/admin/doc-stats/${d.id}`} className="block">
                      <div className="font-medium text-slate-200 group-hover:text-white truncate max-w-[260px]">
                        {d.filename ?? "—"}
                      </div>
                      <div className="text-[11px] text-slate-500">
                        {d.clientName ?? "—"}{d.batchId != null ? ` · batch #${d.batchId}` : ""}
                      </div>
                    </Link>
                  </td>
                  <td className="px-4 py-3">{d.qcDecision ? <StatusBadge status={d.qcDecision} size="xs" /> : "—"}</td>
                  <td className={`px-4 py-3 text-right tabular-nums font-medium ${durationTone(d.totalMs)}`}>{fmtMs(d.totalMs)}</td>
                  <td className={`px-4 py-3 text-right tabular-nums ${durationTone(d.ruleEngineMs)}`}>{fmtMs(d.ruleEngineMs)}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-400">{d.ruleCount ?? "—"}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5 text-slate-300">
                      <Layers size={12} className="text-slate-500 shrink-0" />
                      <span className="truncate max-w-[150px]">{d.slowestStageLabel ?? "—"}</span>
                      <span className="text-slate-500 tabular-nums">{fmtMs(d.slowestStageMs)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5 text-slate-300">
                      <Gauge size={12} className="text-slate-500 shrink-0" />
                      <span className="font-mono text-[12px]">{d.slowestRuleId ?? "—"}</span>
                      <span className="text-slate-500 tabular-nums">{fmtMs(d.slowestRuleMs)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link href={`/admin/doc-stats/${d.id}`} className="inline-flex items-center text-slate-500 transition-colors group-hover:text-indigo-300">
                      <ArrowRight size={15} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {total > 1 && (
        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="inline-flex h-8 items-center gap-1 rounded-md border border-white/10 bg-[#11161C] px-3 text-xs text-slate-300 disabled:opacity-40 hover:border-white/20"
          >
            <ChevronLeft size={14} /> Prev
          </button>
          <span className="text-xs text-slate-500 tabular-nums">Page {page + 1} of {total}</span>
          <button
            onClick={() => setPage((p) => Math.min(total - 1, p + 1))}
            disabled={page >= total - 1}
            className="inline-flex h-8 items-center gap-1 rounded-md border border-white/10 bg-[#11161C] px-3 text-xs text-slate-300 disabled:opacity-40 hover:border-white/20"
          >
            Next <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

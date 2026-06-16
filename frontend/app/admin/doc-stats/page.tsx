"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Search, Timer, ChevronLeft, ChevronRight, Gauge, FileSearch, ArrowRight,
  Cpu, Hourglass, AlertTriangle, ListOrdered, Boxes, TrendingUp,
} from "lucide-react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from "recharts";
import {
  getDocStats, getDocStatBatches, getDocStatRuleRanking, getDocStatTrend,
  type DocStatSummary, type DocStatBatchRollup, type DocStatRuleRank, type Pctl,
  type DocStatTrendPoint,
} from "@/lib/api";
import { fmtMs, durationTone } from "@/lib/duration";
import { TableSkeleton } from "@/components/shared/Skeleton";
import EmptyState from "@/components/shared/EmptyState";
import StatusBadge from "@/components/shared/StatusBadge";
import { toast } from "@/lib/toast";

type View = "appraisals" | "batches" | "ranking" | "trend";

const TABS: { key: View; label: string; Icon: typeof Timer }[] = [
  { key: "appraisals", label: "Appraisals", Icon: FileSearch },
  { key: "batches",    label: "Batches",    Icon: Boxes },
  { key: "ranking",    label: "Rule ranking", Icon: ListOrdered },
  { key: "trend",      label: "Trend",      Icon: TrendingUp },
];

export default function DocStatsPage() {
  const [view, setView] = useState<View>("appraisals");

  return (
    <div className="p-6 lg:p-8 max-w-[1400px] mx-auto">
      <header className="mb-5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-indigo-500/25 bg-indigo-600/15">
            <Timer size={18} className="text-indigo-300" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-white">DocStats — QC timing</h1>
            <p className="text-xs text-slate-500">
              Real measured time per pipeline stage and QC rule. Groq calls are split into model
              inference vs throttle wait, so a frequency problem looks different from a size problem.
            </p>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="mb-5 flex items-center gap-1 border-b border-white/10">
        {TABS.map(({ key, label, Icon }) => (
          <button
            key={key}
            onClick={() => setView(key)}
            className={`relative -mb-px flex items-center gap-1.5 px-3.5 py-2 text-sm transition-colors ${
              view === key ? "text-white" : "text-slate-500 hover:text-slate-300"
            }`}
          >
            <Icon size={14} /> {label}
            {view === key && <span className="absolute inset-x-0 -bottom-px h-0.5 rounded-t bg-indigo-400" />}
          </button>
        ))}
      </div>

      {view === "appraisals" && <AppraisalsPanel />}
      {view === "batches" && <BatchesPanel />}
      {view === "ranking" && <RankingPanel />}
      {view === "trend" && <TrendPanel />}
    </div>
  );
}

/* ── Appraisals: searchable per-file list ─────────────────────────────────── */
function AppraisalsPanel() {
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
      setRows(res.content); setTotal(Math.max(1, res.totalPages)); setCount(res.totalElements);
    } catch { toast.error("Failed to load docStats"); }
    finally { setLoading(false); }
  }, [page, query]);

  useEffect(() => {
    const t = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(t);
  }, [load]);
  useEffect(() => {
    const t = window.setTimeout(() => { setPage(0); setQuery(search); }, 300);
    return () => window.clearTimeout(t);
  }, [search]);

  return (
    <>
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

      <div className="overflow-hidden rounded-xl border border-white/10 bg-[#11161C]/60">
        {loading ? (
          <div className="p-4"><TableSkeleton rows={8} /></div>
        ) : rows.length === 0 ? (
          <EmptyState icon={FileSearch}
            title={query ? "No matching appraisals" : "No QC timings yet"}
            description={query ? "Try a different filename, client, or batch id."
              : "Run QC on a batch — timings are captured automatically for every appraisal."} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-[11px] uppercase tracking-wide text-slate-500">
                <th className="px-4 py-2.5 font-medium">Appraisal</th>
                <th className="px-4 py-2.5 font-medium">Decision</th>
                <th className="px-4 py-2.5 font-medium text-right">Total</th>
                <th className="px-4 py-2.5 font-medium text-right">Rule engine</th>
                <th className="px-4 py-2.5 font-medium">AI (analysis / wait)</th>
                <th className="px-4 py-2.5 font-medium">Slowest rule</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id} className="group border-b border-white/[0.04] transition-colors hover:bg-white/[0.03]">
                  <td className="px-4 py-3">
                    <Link href={`/admin/doc-stats/${d.id}`} className="block">
                      <div className="font-medium text-slate-200 group-hover:text-white truncate max-w-[240px]">{d.filename ?? "—"}</div>
                      <div className="text-[11px] text-slate-500">{d.clientName ?? "—"}{d.batchId != null ? ` · batch #${d.batchId}` : ""}</div>
                    </Link>
                  </td>
                  <td className="px-4 py-3">{d.qcDecision ? <StatusBadge status={d.qcDecision} size="xs" /> : "—"}</td>
                  <td className={`px-4 py-3 text-right tabular-nums font-medium ${durationTone(d.totalMs)}`}>{fmtMs(d.totalMs)}</td>
                  <td className={`px-4 py-3 text-right tabular-nums ${durationTone(d.ruleEngineMs)}`}>{fmtMs(d.ruleEngineMs)}</td>
                  <td className="px-4 py-3">
                    {(d.llmCalls ?? 0) > 0 ? (
                      <div className="flex items-center gap-2 text-[12px]">
                        <span className="flex items-center gap-1 text-sky-300"><Cpu size={11} />{fmtMs(d.llmInferenceMs)}</span>
                        <span className="flex items-center gap-1 text-amber-300"><Hourglass size={11} />{fmtMs(d.llmThrottleWaitMs)}</span>
                        {(d.rateLimitHits ?? 0) > 0 && (
                          <span className="flex items-center gap-0.5 text-red-300" title={`${d.rateLimitHits} rate-limit hit(s)`}>
                            <AlertTriangle size={11} />{d.rateLimitHits}
                          </span>
                        )}
                      </div>
                    ) : <span className="text-slate-600 text-xs">none</span>}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5 text-slate-300">
                      <Gauge size={12} className="text-slate-500 shrink-0" />
                      <span className="font-mono text-[12px]">{d.slowestRuleId ?? "—"}</span>
                      <span className="text-slate-500 tabular-nums">{fmtMs(d.slowestRuleMs)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link href={`/admin/doc-stats/${d.id}`} className="inline-flex items-center text-slate-500 transition-colors group-hover:text-indigo-300"><ArrowRight size={15} /></Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {total > 1 && (
        <div className="mt-4 flex items-center justify-end gap-2">
          <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}
            className="inline-flex h-8 items-center gap-1 rounded-md border border-white/10 bg-[#11161C] px-3 text-xs text-slate-300 disabled:opacity-40 hover:border-white/20">
            <ChevronLeft size={14} /> Prev
          </button>
          <span className="text-xs text-slate-500 tabular-nums">Page {page + 1} of {total}</span>
          <button onClick={() => setPage((p) => Math.min(total - 1, p + 1))} disabled={page >= total - 1}
            className="inline-flex h-8 items-center gap-1 rounded-md border border-white/10 bg-[#11161C] px-3 text-xs text-slate-300 disabled:opacity-40 hover:border-white/20">
            Next <ChevronRight size={14} />
          </button>
        </div>
      )}
    </>
  );
}

/* ── Batches: P50/P95/P99 per batch ───────────────────────────────────────── */
function BatchesPanel() {
  const [rows, setRows] = useState<DocStatBatchRollup[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { setRows(await getDocStatBatches()); }
    catch { toast.error("Failed to load batch rollup"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { const t = window.setTimeout(() => { void load(); }, 0); return () => window.clearTimeout(t); }, [load]);

  const Cell = ({ p }: { p: Pctl }) => (
    <td className="px-3 py-3 text-right tabular-nums">
      <div className={durationTone(p.p50)}>{fmtMs(p.p50)}</div>
      <div className="text-[10px] text-slate-500">p95 {fmtMs(p.p95)} · p99 {fmtMs(p.p99)}</div>
    </td>
  );

  if (loading) return <div className="rounded-xl border border-white/10 bg-[#11161C]/60 p-4"><TableSkeleton rows={6} cols={5} /></div>;
  if (rows.length === 0) return <EmptyState icon={Boxes} title="No batches measured yet" description="Batch percentiles appear once QC has run on at least one batch." />;

  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-[#11161C]/60">
      <div className="border-b border-white/10 px-4 py-2.5 text-[11px] text-slate-500">
        Distribution across each batch&apos;s appraisals — median (p50) with the p95/p99 tail.
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/10 text-left text-[11px] uppercase tracking-wide text-slate-500">
            <th className="px-4 py-2.5 font-medium">Batch</th>
            <th className="px-3 py-2.5 font-medium text-right">Files</th>
            <th className="px-3 py-2.5 font-medium text-right">Total (p50)</th>
            <th className="px-3 py-2.5 font-medium text-right">Rule engine (p50)</th>
            <th className="px-3 py-2.5 font-medium text-right">Pipeline (p50)</th>
            <th className="px-4 py-2.5 font-medium">Last run</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b) => (
            <tr key={b.batchId} className="border-b border-white/[0.04] hover:bg-white/[0.03]">
              <td className="px-4 py-3">
                <div className="font-medium text-slate-200">batch #{b.batchId}</div>
                <div className="text-[11px] text-slate-500">{b.clientName}</div>
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-slate-400">{b.appraisalCount}</td>
              <Cell p={b.totalMs} />
              <Cell p={b.ruleEngineMs} />
              <Cell p={b.pipelineMs} />
              <td className="px-4 py-3 text-[11px] text-slate-500">
                {b.lastRun && b.lastRun !== "null" ? new Date(b.lastRun).toLocaleString() : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Rule ranking: cumulative across the corpus ───────────────────────────── */
function RankingPanel() {
  const [rows, setRows] = useState<DocStatRuleRank[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { setRows(await getDocStatRuleRanking()); }
    catch { toast.error("Failed to load rule ranking"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { const t = window.setTimeout(() => { void load(); }, 0); return () => window.clearTimeout(t); }, [load]);

  if (loading) return <div className="rounded-xl border border-white/10 bg-[#11161C]/60 p-4"><TableSkeleton rows={8} cols={6} /></div>;
  if (rows.length === 0) return <EmptyState icon={ListOrdered} title="No rule timings yet" description="Cumulative rule ranking builds up as QC runs accumulate." />;

  const maxAvg = Math.max(...rows.map(r => r.avgMs), 1);

  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-[#11161C]/60">
      <div className="border-b border-white/10 px-4 py-2.5 text-[11px] text-slate-500">
        Average evaluation time per rule across every measured run — where to focus optimization. LLM% = share of runs where the rule made a Groq call.
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/10 text-left text-[11px] uppercase tracking-wide text-slate-500">
            <th className="px-4 py-2.5 font-medium">Rule</th>
            <th className="px-4 py-2.5 font-medium">Section</th>
            <th className="px-4 py-2.5 font-medium text-right">Avg time</th>
            <th className="px-4 py-2.5 font-medium">Distribution</th>
            <th className="px-4 py-2.5 font-medium text-right">AI calls</th>
            <th className="px-4 py-2.5 font-medium text-right">AI %</th>
            <th className="px-4 py-2.5 font-medium text-right" title="Average rule confidence">Conf.</th>
            <th className="px-4 py-2.5 font-medium text-right">Runs</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ruleId} className="border-b border-white/[0.04] hover:bg-white/[0.03]">
              <td className="px-4 py-2.5">
                <div className="font-mono text-[12px] text-slate-300">{r.ruleId}</div>
                <div className="text-[11px] text-slate-500 truncate max-w-[260px]">{r.ruleName}</div>
              </td>
              <td className="px-4 py-2.5 text-[12px] text-slate-500">{r.section}</td>
              <td className={`px-4 py-2.5 text-right tabular-nums font-medium ${durationTone(r.avgMs)}`}>{fmtMs(r.avgMs)}</td>
              <td className="px-4 py-2.5">
                <div className="h-1.5 w-28 overflow-hidden rounded-full bg-white/[0.04]">
                  <div className="h-full rounded-full bg-gradient-to-r from-indigo-500/70 to-sky-400/70"
                    style={{ width: `${Math.max(2, (r.avgMs / maxAvg) * 100)}%` }} />
                </div>
              </td>
              <td className="px-4 py-2.5 text-right tabular-nums text-slate-400">{r.llmCalls}</td>
              <td className="px-4 py-2.5 text-right tabular-nums">
                <span className={r.pctLlm > 0 ? "text-amber-300" : "text-slate-600"}>{r.pctLlm}%</span>
              </td>
              <td className="px-4 py-2.5 text-right tabular-nums text-slate-400">
                {(r.avgConfidence * 100).toFixed(0)}%
              </td>
              <td className="px-4 py-2.5 text-right tabular-nums text-slate-500">{r.runs}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Trend: total / inference / throttle across successive runs ───────────── */
function TrendPanel() {
  const [rows, setRows] = useState<DocStatTrendPoint[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { setRows(await getDocStatTrend(undefined, 40)); }
    catch { toast.error("Failed to load trend"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { const t = window.setTimeout(() => { void load(); }, 0); return () => window.clearTimeout(t); }, [load]);

  if (loading) return <div className="rounded-xl border border-white/10 bg-[#11161C]/60 p-4"><TableSkeleton rows={6} cols={3} /></div>;
  if (rows.length === 0) return <EmptyState icon={TrendingUp} title="No runs to trend yet" description="The trend builds up as QC runs accumulate — re-run a batch to see if an optimization landed." />;

  // chart in seconds for readability; index the runs chronologically
  const data = rows.map((r, i) => ({
    idx: i + 1,
    at: r.at && r.at !== "null" ? new Date(r.at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : `#${i + 1}`,
    total: +(r.totalMs / 1000).toFixed(2),
    inference: +(r.inferenceMs / 1000).toFixed(2),
    throttle: +(r.throttleWaitMs / 1000).toFixed(2),
  }));

  return (
    <div className="rounded-xl border border-white/10 bg-[#11161C]/60 p-5">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-white">
        <TrendingUp size={15} className="text-indigo-300" /> Processing-time trend
      </h2>
      <p className="mb-4 text-[11px] text-slate-500">
        Last {rows.length} runs, oldest → newest (seconds). Watch total fall after an optimization — and whether throttle-wait, not inference, is what&apos;s moving.
      </p>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 6, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#ffffff0a" />
          <XAxis dataKey="at" tick={{ fill: "#64748b", fontSize: 9 }} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={28} />
          <YAxis tick={{ fill: "#64748b", fontSize: 9 }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}s`} />
          <Tooltip
            contentStyle={{ background: "#0f141a", border: "1px solid #ffffff14", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#cbd5e1" }} formatter={(v, n) => [`${v}s`, String(n)]} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Line type="monotone" dataKey="total"     name="Total"          stroke="#818cf8" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="inference" name="LLM inference"  stroke="#38bdf8" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="throttle"  name="LLM throttle"   stroke="#fbbf24" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

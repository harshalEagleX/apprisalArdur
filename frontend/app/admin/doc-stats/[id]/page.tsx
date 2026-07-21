"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft, Timer, Layers, Gauge, Search, ArrowUpDown, Cpu, FileText,
  Hourglass, AlertTriangle, Info, DollarSign,
} from "lucide-react";
import {
  getDocStatDetail, getDocStatThresholds, getDocStatCompare,
  type DocStatDetail, type DocStatRule, type DocStatStage, type DocStatCompare,
} from "@/lib/api";
import { fmtMs, durationTone, fmtCost, fmtTokens } from "@/lib/duration";
import { stageLabel } from "@/lib/stageLabels";
import { Skeleton } from "@/components/shared/Skeleton";
import StatusBadge from "@/components/shared/StatusBadge";
import { toast } from "@/lib/toast";

type SortKey = "ms" | "ruleId" | "section" | "status";
type DetailTab = "overview" | "diagnostics";

/** Sortable table header — hoisted out of the page so it isn't recreated on render. */
function SortTh({ k, children, right, sortKey, onSort }: {
  k: SortKey; children: React.ReactNode; right?: boolean;
  sortKey: SortKey; onSort: (k: SortKey) => void;
}) {
  return (
    <th className={`px-4 py-2.5 font-medium ${right ? "text-right" : "text-left"}`}>
      <button
        onClick={() => onSort(k)}
        className={`inline-flex items-center gap-1 transition-colors hover:text-slate-200 ${sortKey === k ? "text-slate-200" : ""}`}
      >
        {children}
        <ArrowUpDown size={11} className={sortKey === k ? "text-indigo-300" : "text-slate-600"} />
      </button>
    </th>
  );
}

/** A labelled horizontal bar — width is the share of the largest value in its group. */
function Bar({ label, ms, pct, max, sub }: {
  label: string; ms: number; pct: number; max: number; sub?: string;
}) {
  const width = max > 0 ? Math.max(2, (ms / max) * 100) : 0;
  return (
    <div className="group">
      <div className="mb-1 flex items-center justify-between gap-3 text-xs">
        <span className="truncate text-slate-300">{label}</span>
        <span className="flex shrink-0 items-center gap-2 tabular-nums">
          {sub && <span className="text-slate-600">{sub}</span>}
          <span className={durationTone(ms)}>{fmtMs(ms)}</span>
          <span className="w-10 text-right text-slate-600">{pct.toFixed(1)}%</span>
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/[0.04]">
        <div className="h-full rounded-full bg-gradient-to-r from-indigo-500/70 to-sky-400/70 transition-all"
          style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

/** Stage bar: like Bar, but flags over-threshold (red) and, for LLM stages,
 *  splits the fill into inference (model) vs throttle-wait (queue/rate-limit). */
function StageBar({ s, max, threshold }: { s: DocStatStage; max: number; threshold?: number }) {
  const width = max > 0 ? Math.max(2, (s.ms / max) * 100) : 0;
  const over = threshold != null && s.ms > threshold;
  const hasLlm = s.llmCalls > 0 && (s.inferenceMs + s.throttleWaitMs) > 0;
  // within the bar, show the inference vs throttle proportion of the LLM time
  const llmTotal = s.inferenceMs + s.throttleWaitMs || 1;
  const infPct = (s.inferenceMs / llmTotal) * 100;
  return (
    <div className="group">
      <div className="mb-1 flex items-center justify-between gap-3 text-xs">
        <span className="flex items-center gap-1.5 truncate text-slate-300">
          {label_(stageLabel(s.stage, s.label))}
          {over && <AlertTriangle size={11} className="shrink-0 text-red-400" />}
        </span>
        <span className="flex shrink-0 items-center gap-2 tabular-nums">
          {hasLlm && (
            <span className="flex items-center gap-1.5 text-[10px]">
              <span className="flex items-center gap-0.5 text-sky-300" title="AI analysis time"><Cpu size={10} />{fmtMs(s.inferenceMs)}</span>
              <span className="flex items-center gap-0.5 text-amber-300" title="time spent waiting on the AI rate limit"><Hourglass size={10} />{fmtMs(s.throttleWaitMs)}</span>
            </span>
          )}
          <span className={over ? "text-red-300" : durationTone(s.ms)}>{fmtMs(s.ms)}</span>
          <span className="w-10 text-right text-slate-600">{s.pctOfPipeline.toFixed(1)}%</span>
        </span>
      </div>
      <div className={`h-2 w-full overflow-hidden rounded-full bg-white/[0.04] ${over ? "ring-1 ring-red-500/40" : ""}`}>
        {hasLlm ? (
          <div className="flex h-full" style={{ width: `${width}%` }}>
            <div className="h-full bg-sky-400/70" style={{ width: `${infPct}%` }} title="AI analysis" />
            <div className="h-full bg-amber-400/70" style={{ width: `${100 - infPct}%` }} title="waiting on rate limit" />
          </div>
        ) : (
          <div className={`h-full rounded-full transition-all ${over ? "bg-red-500/70" : "bg-gradient-to-r from-indigo-500/70 to-sky-400/70"}`}
            style={{ width: `${width}%` }} />
        )}
      </div>
    </div>
  );
}

function label_(s: string) { return <span className="truncate">{s}</span>; }

export default function DocStatDetailPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [data, setData]     = useState<DocStatDetail | null>(null);
  const [thresholds, setThresholds] = useState<Record<string, number>>({});
  const [compare, setCompare] = useState<DocStatCompare | null>(null);
  const [loading, setLoad]  = useState(true);
  const [detailTab, setDetailTab] = useState<DetailTab>("overview");
  const [ruleSearch, setRuleSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("ms");
  const [sortAsc, setSortAsc] = useState(false);

  const load = useCallback(async () => {
    if (!Number.isFinite(id)) return;
    setLoad(true);
    try {
      const [d, th, cmp] = await Promise.all([
        getDocStatDetail(id),
        getDocStatThresholds().catch(() => ({} as Record<string, number>)),
        getDocStatCompare(id).catch(() => null),
      ]);
      setData(d); setThresholds(th); setCompare(cmp);
    } catch { toast.error("Failed to load timing detail"); }
    finally { setLoad(false); }
  }, [id]);

  useEffect(() => {
    const t = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(t);
  }, [load]);

  const stageMax   = useMemo(() => Math.max(0, ...(data?.stages ?? []).map(s => s.ms)), [data]);
  const sectionMax = useMemo(() => Math.max(0, ...(data?.sections ?? []).map(s => s.ms)), [data]);

  const sortedRules = useMemo(() => {
    const list = (data?.rules ?? []).filter(r => {
      if (!ruleSearch) return true;
      const q = ruleSearch.toLowerCase();
      return r.ruleId.toLowerCase().includes(q)
        || r.ruleName.toLowerCase().includes(q)
        || r.section.toLowerCase().includes(q);
    });
    const dir = sortAsc ? 1 : -1;
    return [...list].sort((a, b) => {
      if (sortKey === "ms") return (a.ms - b.ms) * dir;
      const av = String(a[sortKey] ?? ""), bv = String(b[sortKey] ?? "");
      return av.localeCompare(bv) * dir;
    });
  }, [data, ruleSearch, sortKey, sortAsc]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortAsc(a => !a);
    else { setSortKey(key); setSortAsc(key !== "ms"); }
  }

  if (loading) {
    return (
      <div className="p-6 lg:p-8 max-w-[1200px] mx-auto space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="p-8 text-center text-slate-400">
        <p>Timing record not found.</p>
        <Link href="/admin/doc-stats" className="mt-3 inline-block text-indigo-300 hover:underline">← Back to DocStats</Link>
      </div>
    );
  }

  return (
    <div className="w-full max-w-[1800px] p-6 lg:p-8">
      {/* Breadcrumb */}
      <nav className="mb-4 flex items-center gap-1.5 text-xs text-slate-500">
        <Link href="/admin/doc-stats" className="inline-flex items-center gap-1 transition-colors hover:text-slate-300">
          <ArrowLeft size={12} /> DocStats
        </Link>
        <span className="text-slate-600">/</span>
        <span className="max-w-[280px] truncate text-slate-300" title={data.filename ?? undefined}>{data.filename ?? "Document"}</span>
      </nav>

      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-indigo-500/25 bg-indigo-600/15">
            <FileText size={18} className="text-indigo-300" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold text-white">{data.filename ?? "—"}</h1>
            <p className="text-xs text-slate-500">
              {data.clientName ?? "—"}
              {data.batchId != null && <> · <Link href="/admin/batches" className="hover:text-slate-300">batch #{data.batchId}</Link></>}
              {data.createdAt && <> · {new Date(data.createdAt).toLocaleString()}</>}
            </p>
          </div>
        </div>
        {data.qcDecision && <StatusBadge status={data.qcDecision} />}
      </header>

      {/* Tab bar — Overview (pipeline+sections) vs Diagnostics (per-rule timing) */}
      <div className="mb-5 flex items-center gap-1 border-b border-white/10">
        {(["overview", "diagnostics"] as DetailTab[]).map(tab => (
          <button
            key={tab}
            onClick={() => setDetailTab(tab)}
            className={`relative -mb-px flex items-center gap-1.5 px-3.5 py-2 text-sm capitalize transition-colors ${
              detailTab === tab ? "text-white" : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {tab === "overview" ? <Layers size={13} /> : <Search size={13} />}
            {tab === "overview" ? "Overview" : "Diagnostics"}
            {tab === "diagnostics" && data.rules.length > 0 && (
              <span className="ml-1 rounded bg-slate-700/60 px-1.5 py-0.5 text-[10px] tabular-nums text-slate-400">
                {data.rules.length} rules
              </span>
            )}
            {detailTab === tab && <span className="absolute inset-x-0 -bottom-px h-0.5 rounded-t bg-indigo-400" />}
          </button>
        ))}
      </div>

      {/* Overview tab: headline numbers + insight + compare + pipeline + sections */}
      {/* Headline numbers — total, rule engine, the AI inference/throttle split, and $ cost */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <HeadStat icon={Timer} label="Total time"   value={fmtMs(data.totalMs)} hint="end-to-end" tone="text-white" />
        <HeadStat icon={Cpu}   label="Rule engine"  value={fmtMs(data.ruleEngineMs)} hint={`${data.ruleCount ?? 0} rules`} tone="text-sky-300" />
        <HeadStat icon={Cpu}   label="AI analysis" value={fmtMs(data.llmInferenceMs)} hint={`${data.llmCalls ?? 0} AI call${(data.llmCalls ?? 0) === 1 ? "" : "s"}`} tone="text-sky-300" />
        <HeadStat icon={Hourglass} label="Rate-limit wait" value={fmtMs(data.llmThrottleWaitMs)}
          hint={(data.rateLimitHits ?? 0) > 0 ? `${data.rateLimitHits} rate-limit hit(s)` : "no rate-limit hits"}
          tone={(data.rateLimitHits ?? 0) > 0 ? "text-red-300" : "text-amber-300"} />
        <HeadStat icon={DollarSign} label="AI cost" value={fmtCost(data.llmCostUsd)}
          hint={(data.totalTokens ?? 0) > 0 ? `${fmtTokens(data.totalTokens)} tokens` : "no tokens billed"}
          tone="text-emerald-300" />
      </div>

      {/* "So what?" — interpret the dominant cost and recommend an action, so the numbers
          drive a decision instead of just reporting milliseconds. */}
      {(data.totalMs ?? 0) > 0 && (() => {
        const total = data.totalMs ?? 0;
        const pctT = Math.round(((data.llmThrottleWaitMs ?? 0) / total) * 100);
        const pctI = Math.round(((data.llmInferenceMs ?? 0) / total) * 100);
        const pctE = Math.round(((data.ruleEngineMs ?? 0) / total) * 100);
        let tone = "border-white/10 bg-surface/60 text-slate-300";
        let headline: string; let rec: string;
        if (pctT >= 30) {
          tone = "border-amber-500/30 bg-amber-950/20 text-amber-200";
          headline = `${pctT}% of processing was spent waiting on the AI rate limit.`;
          rec = "Add another TOGETHER_API_KEY (rate limits are per key) or reduce concurrent QC jobs so requests aren't throttled.";
        } else if (pctI >= 40) {
          tone = "border-sky-500/30 bg-sky-950/20 text-sky-200";
          headline = `${pctI}% of processing was AI analysis (${data.llmCalls ?? 0} call${(data.llmCalls ?? 0) === 1 ? "" : "s"}).`;
          rec = "Reduce prompt size or pre-filter candidates before the LLM to cut inference time.";
        } else if (pctE >= 50) {
          headline = `${pctE}% of processing was the local rule engine.`;
          rec = "Mostly local compute — no AI-provider bottleneck. Profile the slowest rules below if you need to trim it.";
        } else {
          tone = "border-green-500/25 bg-green-950/15 text-green-200";
          headline = "No single stage dominates — this run is healthy.";
          rec = "Rule engine, AI analysis, and rate-limit wait are balanced.";
        }
        return (
          <div className={`mb-6 flex items-start gap-2.5 rounded-xl border p-4 ${tone}`}>
            <Info size={15} className="mt-0.5 flex-shrink-0 opacity-80" />
            <div>
              <div className="text-sm font-semibold">{headline}</div>
              <div className="mt-0.5 text-xs opacity-80">{rec}</div>
            </div>
          </div>
        );
      })()}

      {/* Before/after vs the run this superseded (same file re-QC'd) */}
      {compare?.previous && compare.delta && (
        <div className="mb-6 rounded-xl border border-white/10 bg-surface/60 p-4">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
            <ArrowUpDown size={15} className="text-indigo-300" /> Versus previous run
            <span className="text-[11px] font-normal text-slate-500">
              re-QC of the same file · prior run {compare.previous.createdAt ? new Date(compare.previous.createdAt).toLocaleString() : ""}
            </span>
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <DeltaCard label="Total" d={compare.delta.totalMs} />
            <DeltaCard label="Rule engine" d={compare.delta.ruleEngineMs} />
            <DeltaCard label="AI analysis" d={compare.delta.llmInferenceMs} />
            <DeltaCard label="Rate-limit wait" d={compare.delta.llmThrottleWaitMs} />
          </div>
        </div>
      )}

      {detailTab === "overview" && (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Pipeline stages */}
          <section className="rounded-xl border border-white/10 bg-surface/60 p-5">
            <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-white">
              <Layers size={15} className="text-indigo-300" /> Pipeline stages
            </h2>
            <p className="mb-3 flex items-center gap-1.5 text-[11px] text-slate-500">
              <Info size={11} /> Stages run one after another — total time is their sum. Blue = AI analysis, amber = waiting on the AI rate limit; red = slower than expected.
            </p>
            <div className="space-y-3">
              {data.stages.length === 0 && <p className="text-xs text-slate-500">No stage timings recorded.</p>}
              {data.stages.map((s) => (
                <StageBar key={s.stage} s={s} max={stageMax} threshold={thresholds[s.stage]} />
              ))}
            </div>
          </section>

          {/* QC sections */}
          <section className="rounded-xl border border-white/10 bg-surface/60 p-5">
            <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-white">
              <Gauge size={15} className="text-indigo-300" /> QC sections
            </h2>
            <p className="mb-4 text-[11px] text-slate-500">Rule-engine time by section (% of rule engine).</p>
            <div className="space-y-3">
              {data.sections.length === 0 && <p className="text-xs text-slate-500">No section timings recorded.</p>}
              {data.sections.map((s) => (
                <Bar key={s.section} label={s.label} ms={s.ms} pct={s.pctOfRules} max={sectionMax} sub={`${s.ruleCount} rules`} />
              ))}
            </div>
          </section>
        </div>
      )}

      {detailTab === "diagnostics" && (
        <section className="overflow-hidden rounded-xl border border-white/10 bg-surface/60">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-3">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
                <Cpu size={15} className="text-indigo-300" /> Per-rule timing
                <span className="text-[11px] font-normal text-slate-500">({sortedRules.length} of {data.rules.length})</span>
              </h2>
              <p className="mt-0.5 text-[11px] text-slate-500">
                Engineer-grade breakdown — how long each rule took and whether AI was involved.
              </p>
            </div>
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                value={ruleSearch}
                onChange={(e) => setRuleSearch(e.target.value)}
                placeholder="Filter rules…"
                className="h-8 w-56 rounded-md border border-white/10 bg-sunken pl-8 pr-2 text-xs text-white placeholder:text-slate-600 focus:border-indigo-500/40 focus:outline-none"
              />
            </div>
          </div>
          <div className="max-h-[620px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface text-[11px] uppercase tracking-wide text-slate-500">
                <tr className="border-b border-white/10">
                  <SortTh k="ruleId" sortKey={sortKey} onSort={toggleSort}>Rule</SortTh>
                  <th className="px-4 py-2.5 text-left font-medium">Name</th>
                  <SortTh k="section" sortKey={sortKey} onSort={toggleSort}>Section</SortTh>
                  <SortTh k="status" sortKey={sortKey} onSort={toggleSort}>Finding</SortTh>
                  <th className="px-4 py-2.5 text-right font-medium">AI</th>
                  <SortTh k="ms" right sortKey={sortKey} onSort={toggleSort}>Time</SortTh>
                </tr>
              </thead>
              <tbody>
                {sortedRules.map((r: DocStatRule, i) => (
                  <tr key={`${r.ruleId}-${i}`} className="border-b border-white/[0.04] hover:bg-white/[0.03]">
                    <td className="px-4 py-2.5 font-mono text-[12px] text-slate-300">{r.ruleId}</td>
                    <td className="px-4 py-2.5 text-slate-400 max-w-[300px] truncate">{r.ruleName}</td>
                    <td className="px-4 py-2.5 text-[12px] text-slate-500">{r.section}</td>
                    <td className="px-4 py-2.5">{r.status ? <StatusBadge status={r.status} size="xs" /> : "—"}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-[12px]">
                      {r.llmCalls > 0
                        ? <span className="text-sky-300" title={`${r.llmCalls} AI call(s), ${fmtMs(r.throttleMs)} waiting on rate limit`}>{r.llmCalls}× · {fmtMs(r.llmMs)}</span>
                        : <span className="text-slate-600">—</span>}
                    </td>
                    <td className={`px-4 py-2.5 text-right tabular-nums ${durationTone(r.ms)}`}>{fmtMs(r.ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

/** Before/after delta tile — green when the current run got faster, red when slower. */
function DeltaCard({ label, d }: { label: string; d: { current: number; previous: number; deltaMs: number; pct: number } }) {
  const faster = d.deltaMs < 0;
  const flat = Math.abs(d.deltaMs) < 1;
  const tone = flat ? "text-slate-400" : faster ? "text-green-300" : "text-red-300";
  const sign = d.deltaMs > 0 ? "+" : "";
  return (
    <div className="rounded-lg border border-white/10 bg-sunken p-3">
      <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-base font-semibold tabular-nums text-white">{fmtMs(d.current)}</div>
      <div className={`text-[11px] tabular-nums ${tone}`}>
        {flat ? "no change" : `${sign}${fmtMs(Math.abs(d.deltaMs))} (${sign}${d.pct}%)`} vs {fmtMs(d.previous)}
      </div>
    </div>
  );
}

function HeadStat({ icon: Icon, label, value, hint, tone }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string; value: string; hint: string; tone: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-surface/60 p-4">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-500">
        <Icon size={13} /> {label}
      </div>
      <div className={`text-xl font-semibold tabular-nums ${tone}`}>{value}</div>
      <div className="mt-0.5 truncate text-[11px] text-slate-500">{hint}</div>
    </div>
  );
}

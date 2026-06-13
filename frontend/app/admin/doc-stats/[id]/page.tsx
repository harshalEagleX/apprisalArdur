"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft, Timer, Layers, Gauge, Search, ArrowUpDown, Cpu, FileText,
} from "lucide-react";
import { getDocStatDetail, type DocStatDetail, type DocStatRule } from "@/lib/api";
import { fmtMs, durationTone } from "@/lib/duration";
import { Skeleton } from "@/components/shared/Skeleton";
import StatusBadge from "@/components/shared/StatusBadge";
import { toast } from "@/lib/toast";

type SortKey = "ms" | "ruleId" | "section" | "status";

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
        <div
          className="h-full rounded-full bg-gradient-to-r from-indigo-500/70 to-sky-400/70 transition-all"
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

export default function DocStatDetailPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [data, setData]     = useState<DocStatDetail | null>(null);
  const [loading, setLoad]  = useState(true);
  const [ruleSearch, setRuleSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("ms");
  const [sortAsc, setSortAsc] = useState(false);

  const load = useCallback(async () => {
    if (!Number.isFinite(id)) return;
    setLoad(true);
    try { setData(await getDocStatDetail(id)); }
    catch { toast.error("Failed to load timing detail"); }
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
    <div className="p-6 lg:p-8 max-w-[1200px] mx-auto">
      {/* Back + header */}
      <Link href="/admin/doc-stats" className="mb-4 inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200">
        <ArrowLeft size={14} /> DocStats
      </Link>

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

      {/* Headline numbers */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <HeadStat icon={Timer} label="Total time"   value={fmtMs(data.totalMs)} hint="end-to-end" tone="text-white" />
        <HeadStat icon={Cpu}   label="Rule engine"  value={fmtMs(data.ruleEngineMs)} hint={`${data.ruleCount ?? 0} rules`} tone="text-sky-300" />
        <HeadStat icon={Layers} label="Slowest stage" value={fmtMs(data.slowestStageMs)} hint={data.slowestStageLabel ?? "—"} tone="text-amber-300" />
        <HeadStat icon={Gauge} label="Slowest rule"  value={fmtMs(data.slowestRuleMs)} hint={data.slowestRuleId ?? "—"} tone="text-amber-300" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Pipeline stages */}
        <section className="rounded-xl border border-white/10 bg-[#11161C]/60 p-5">
          <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-white">
            <Layers size={15} className="text-indigo-300" /> Pipeline stages
          </h2>
          <p className="mb-4 text-[11px] text-slate-500">Where end-to-end time was spent (extraction → rules).</p>
          <div className="space-y-3">
            {data.stages.length === 0 && <p className="text-xs text-slate-500">No stage timings recorded.</p>}
            {data.stages.map((s) => (
              <Bar key={s.stage} label={s.label} ms={s.ms} pct={s.pctOfPipeline} max={stageMax} />
            ))}
          </div>
        </section>

        {/* QC sections */}
        <section className="rounded-xl border border-white/10 bg-[#11161C]/60 p-5">
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

      {/* Per-rule table */}
      <section className="mt-6 overflow-hidden rounded-xl border border-white/10 bg-[#11161C]/60">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
            <Cpu size={15} className="text-indigo-300" /> Per-rule timing
            <span className="text-[11px] font-normal text-slate-500">({sortedRules.length} of {data.rules.length})</span>
          </h2>
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              value={ruleSearch}
              onChange={(e) => setRuleSearch(e.target.value)}
              placeholder="Filter rules…"
              className="h-8 w-56 rounded-md border border-white/10 bg-[#0c1014] pl-8 pr-2 text-xs text-white placeholder:text-slate-600 focus:border-indigo-500/40 focus:outline-none"
            />
          </div>
        </div>
        <div className="max-h-[520px] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-[#11161C] text-[11px] uppercase tracking-wide text-slate-500">
              <tr className="border-b border-white/10">
                <SortTh k="ruleId" sortKey={sortKey} onSort={toggleSort}>Rule</SortTh>
                <th className="px-4 py-2.5 text-left font-medium">Name</th>
                <SortTh k="section" sortKey={sortKey} onSort={toggleSort}>Section</SortTh>
                <SortTh k="status" sortKey={sortKey} onSort={toggleSort}>Status</SortTh>
                <SortTh k="ms" right sortKey={sortKey} onSort={toggleSort}>Time</SortTh>
              </tr>
            </thead>
            <tbody>
              {sortedRules.map((r: DocStatRule, i) => (
                <tr key={`${r.ruleId}-${i}`} className="border-b border-white/[0.04] hover:bg-white/[0.03]">
                  <td className="px-4 py-2.5 font-mono text-[12px] text-slate-300">{r.ruleId}</td>
                  <td className="px-4 py-2.5 text-slate-400 max-w-[320px] truncate">{r.ruleName}</td>
                  <td className="px-4 py-2.5 text-[12px] text-slate-500">{r.section}</td>
                  <td className="px-4 py-2.5">{r.status ? <StatusBadge status={r.status} size="xs" /> : "—"}</td>
                  <td className={`px-4 py-2.5 text-right tabular-nums ${durationTone(r.ms)}`}>{fmtMs(r.ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function HeadStat({ icon: Icon, label, value, hint, tone }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string; value: string; hint: string; tone: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-[#11161C]/60 p-4">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-500">
        <Icon size={13} /> {label}
      </div>
      <div className={`text-xl font-semibold tabular-nums ${tone}`}>{value}</div>
      <div className="mt-0.5 truncate text-[11px] text-slate-500">{hint}</div>
    </div>
  );
}

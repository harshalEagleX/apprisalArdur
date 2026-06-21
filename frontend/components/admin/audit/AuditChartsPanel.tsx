"use client";
import { useEffect, useState, useCallback } from "react";
import {
  BarChart2, TrendingUp, Layers, AlertTriangle,
  RefreshCw, ChevronDown, Users, Activity,
} from "lucide-react";
import dynamic from "next/dynamic";
import type { AnalyticsOverview, MlInsights, TrendPoint, SlaDashboard } from "./types";
import { JAVA } from "@/lib/config";

const TrendChart    = dynamic(() => import("./charts/TrendChart"),    { ssr: false });
const DecisionDonut = dynamic(() => import("./charts/DecisionDonut"), { ssr: false });
const FileVolumeBar = dynamic(() => import("./charts/FileVolumeBar"), { ssr: false });
const OcrMethodBar  = dynamic(() => import("./charts/OcrMethodBar"),  { ssr: false });
const OperatorBar   = dynamic(() => import("./charts/OperatorBar"),   { ssr: false });

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${JAVA}${path}`, { credentials: "include" });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json() as Promise<T>;
}

// ── Types for additional data ─────────────────────────────────────────────────
interface OcrInsights {
  avgAccuracy: number | null;
  avgProcessingMs: number | null;
  cacheHits: number;
  extractionMethods: { method: string; count: number }[];
}

// Null-safe formatters — analytics averages are null when no files were processed
// in the window, so render an em dash rather than crashing on .toFixed().
const fmtPct = (v: number | null | undefined, dp = 1): string =>
  v == null || Number.isNaN(v) ? "—" : `${v.toFixed(dp)}%`;
const fmtSec = (v: number | null | undefined, dp = 1): string =>
  v == null || Number.isNaN(v) ? "—" : `${v.toFixed(dp)}s`;
const fmtNum = (v: number | null | undefined): string =>
  v == null || Number.isNaN(v) ? "—" : v.toLocaleString();

interface OperatorInsights {
  activeNow: number;
  operators: { name: string; activeMinutes: number; filesProcessed: number; corrections: number }[];
}

interface AnomalyReport {
  fastDecisionReviewers: { name: string; avgDecisionSeconds: number; decisionCount: number; flag: string }[];
  failOverrideReviewers: { name: string; overrideCount: number; flag: string }[];
}

// ── Compact stat card ─────────────────────────────────────────────────────────
function Stat({ label, value, sub, color = "text-white" }: {
  label: string; value: string | number; sub?: string; color?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-widest text-slate-600">{label}</span>
      <span className={`text-sm font-bold tabular-nums ${color}`}>{value}</span>
      {sub && <span className="text-[10px] text-slate-600">{sub}</span>}
    </div>
  );
}

// ── Collapsible section ───────────────────────────────────────────────────────
function Section({ title, icon: Icon, children, defaultOpen = true }: {
  title: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-white/5">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-white/[0.03] transition-colors"
      >
        <Icon size={11} className="text-slate-500 flex-shrink-0" />
        <span className="text-[10px] uppercase tracking-widest text-slate-500 flex-1">{title}</span>
        <ChevronDown
          size={10}
          className={`text-slate-600 transition-transform ${open ? "" : "-rotate-90"}`}
        />
      </button>
      {open && <div className="px-3 pb-3">{children}</div>}
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────
export default function AuditChartsPanel() {
  const [overview,   setOverview]   = useState<AnalyticsOverview | null>(null);
  const [trend,      setTrend]      = useState<TrendPoint[]>([]);
  const [ml,         setMl]         = useState<MlInsights | null>(null);
  const [sla,        setSla]        = useState<SlaDashboard | null>(null);
  const [ocrData,    setOcrData]    = useState<OcrInsights | null>(null);
  const [operators,  setOperators]  = useState<OperatorInsights | null>(null);
  const [anomalies,  setAnomalies]  = useState<AnomalyReport | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [days,       setDays]       = useState(30);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, tr, mlData, slaData, ocr, ops, anom] = await Promise.allSettled([
        get<AnalyticsOverview>(`/api/analytics/overview?days=${days}`),
        get<TrendPoint[]>(`/api/analytics/trend?days=${days}`),
        get<MlInsights>(`/api/analytics/ml?days=${days}`),
        get<SlaDashboard>("/api/analytics/review-sla"),
        get<OcrInsights>(`/api/analytics/ocr?days=${days}`),
        get<OperatorInsights>(`/api/analytics/operators?days=${days}`),
        get<AnomalyReport>(`/api/analytics/anomalies?days=7`),
      ]);
      if (ov.status     === "fulfilled") setOverview(ov.value);
      if (tr.status     === "fulfilled") setTrend(tr.value ?? []);
      if (mlData.status === "fulfilled") setMl(mlData.value);
      if (slaData.status === "fulfilled") setSla(slaData.value);
      if (ocr.status    === "fulfilled") setOcrData(ocr.value);
      if (ops.status    === "fulfilled") setOperators(ops.value);
      if (anom.status   === "fulfilled") setAnomalies(anom.value);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  return (
    <aside className="w-64 flex-shrink-0 border-l border-white/10 bg-[#0d1117] flex flex-col overflow-y-auto text-white">

      {/* ── Header ───────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-white/10 sticky top-0 bg-[#0d1117] z-10">
        <div className="flex items-center gap-2">
          <BarChart2 size={13} className="text-indigo-400" />
          <span className="text-xs font-semibold">Analytics</span>
        </div>
        <div className="flex items-center gap-1.5">
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            className="bg-transparent border border-white/10 rounded px-1.5 py-0.5 text-[10px] text-slate-400 outline-none cursor-pointer"
          >
            {[7, 14, 30, 90].map(d => (
              <option key={d} value={d}>{d}d</option>
            ))}
          </select>
          <button
            onClick={() => void load()}
            className="text-slate-600 hover:text-white transition-colors"
            title="Refresh"
          >
            <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {loading && !overview ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="text-center">
            <RefreshCw size={16} className="animate-spin text-indigo-400 mx-auto mb-2" />
            <p className="text-[11px] text-slate-600">Loading analytics…</p>
          </div>
        </div>
      ) : (
        <>
          {/* ── Overview KPIs ─────────────────────────────────────────── */}
          <Section title="Overview" icon={Layers}>
            {overview ? (
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                <Stat label="Files"    value={fmtNum(overview.totalFilesProcessed)} />
                <Stat label="Batches"  value={overview.totalBatches} />
                <Stat
                  label="Pass Rate"
                  value={fmtPct(overview.avgRulePassRate)}
                  color="text-green-400"
                />
                <Stat
                  label="OCR Accuracy"
                  value={fmtPct(overview.avgOcrAccuracy)}
                  color="text-indigo-400"
                />
                <Stat
                  label="Avg Process"
                  value={fmtSec(overview.avgProcessingSeconds)}
                  color="text-amber-400"
                />
                <Stat
                  label="Cache Hit"
                  value={fmtPct(overview.cacheHitRate, 0)}
                  color="text-cyan-400"
                />
                {overview.pendingReview > 0 && (
                  <div className="col-span-2">
                    <div className="flex items-center gap-1.5 rounded-md border border-amber-500/20 bg-amber-950/30 px-2 py-1.5">
                      <AlertTriangle size={11} className="text-amber-400 flex-shrink-0" />
                      <span className="text-[11px] text-amber-300 font-semibold">
                        {overview.pendingReview} pending review
                      </span>
                    </div>
                  </div>
                )}
                {overview.activeSessions > 0 && (
                  <div className="col-span-2 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse flex-shrink-0" />
                    <span className="text-[11px] text-green-400">
                      {overview.activeSessions} active session{overview.activeSessions !== 1 ? "s" : ""}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-[11px] text-slate-600">No overview data</p>
            )}
          </Section>

          {/* ── Daily trend — OCR accuracy + pass rate ────────────────── */}
          {trend.length > 0 && (
            <Section title={`${days}d Trend`} icon={TrendingUp}>
              <TrendChart data={trend} />
            </Section>
          )}

          {/* ── File volume ───────────────────────────────────────────── */}
          {trend.length > 0 && (
            <Section title="File Volume" icon={BarChart2} defaultOpen={false}>
              <FileVolumeBar data={trend} />
            </Section>
          )}

          {/* ── QC decision distribution ──────────────────────────────── */}
          <Section title="QC Decisions" icon={Layers} defaultOpen={false}>
            <DecisionDonut data={ml?.decisionBreakdown ?? null} />
            {ml && (
              <div className="mt-2 pt-2 border-t border-white/5">
                <Stat
                  label="Avg Rule Pass Rate"
                  value={fmtPct(ml.avgRulePassRate)}
                  color="text-green-400"
                />
              </div>
            )}
          </Section>

          {/* ── OCR extraction methods ────────────────────────────────── */}
          <Section title="OCR Methods" icon={Activity} defaultOpen={false}>
            {ocrData ? (
              <>
                <OcrMethodBar data={ocrData.extractionMethods ?? []} />
                <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2">
                  <Stat
                    label="Avg Accuracy"
                    value={fmtPct(ocrData.avgAccuracy)}
                    color="text-indigo-400"
                  />
                  <Stat
                    label="Cache Hits"
                    value={fmtNum(ocrData.cacheHits)}
                    color="text-cyan-400"
                  />
                  {ocrData.avgProcessingMs != null && (
                    <Stat
                      label="Avg OCR Time"
                      value={`${(ocrData.avgProcessingMs / 1000).toFixed(1)}s`}
                      color="text-amber-400"
                    />
                  )}
                </div>
              </>
            ) : (
              <p className="text-[11px] text-slate-600">No OCR data</p>
            )}
          </Section>

          {/* ── Operator performance ──────────────────────────────────── */}
          <Section title="Operators" icon={Users} defaultOpen={false}>
            {operators ? (
              <>
                {operators.activeNow > 0 && (
                  <div className="mb-2 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse flex-shrink-0" />
                    <span className="text-[11px] text-green-400">
                      {operators.activeNow} online now
                    </span>
                  </div>
                )}
                <OperatorBar data={operators.operators} />
              </>
            ) : (
              <p className="text-[11px] text-slate-600">No operator data</p>
            )}
          </Section>

          {/* ── SLA alerts ────────────────────────────────────────────── */}
          {sla && (sla.over4Hours > 0 || sla.over8Hours > 0) && (
            <Section title="SLA Alerts" icon={AlertTriangle} defaultOpen>
              <div className="space-y-2">
                {sla.over8Hours > 0 && (
                  <div className="flex items-center justify-between rounded-md bg-red-950/40 border border-red-500/20 px-2 py-1.5">
                    <span className="text-[10px] text-red-300">Over 8h</span>
                    <span className="text-xs font-bold text-red-400">{sla.over8Hours}</span>
                  </div>
                )}
                {sla.over4Hours > 0 && (
                  <div className="flex items-center justify-between rounded-md bg-amber-950/30 border border-amber-500/20 px-2 py-1.5">
                    <span className="text-[10px] text-amber-300">Over 4h</span>
                    <span className="text-xs font-bold text-amber-400">{sla.over4Hours}</span>
                  </div>
                )}
                {sla.items?.slice(0, 4).map(item => (
                  <div key={item.ruleResultId} className="rounded border border-white/5 bg-slate-900/50 px-2 py-1.5">
                    <p className="text-[10px] text-slate-300 truncate" title={item.filename}>
                      {item.filename}
                    </p>
                    <p className="text-[10px] text-slate-600 mt-0.5">
                      {item.ruleId} · {new Date(item.firstPresentedAt).toLocaleDateString()}
                    </p>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* ── Compliance anomalies ──────────────────────────────────── */}
          {anomalies && (
            (anomalies.fastDecisionReviewers?.length > 0 || anomalies.failOverrideReviewers?.length > 0)
          ) && (
            <Section title="Compliance Flags" icon={AlertTriangle} defaultOpen={false}>
              <div className="space-y-2">
                {anomalies.fastDecisionReviewers.map(r => (
                  <div key={r.name} className="rounded border border-amber-500/15 bg-amber-950/20 px-2 py-1.5">
                    <p className="text-[10px] font-medium text-amber-300">{r.name}</p>
                    <p className="text-[10px] text-slate-500 mt-0.5">
                      Avg {r.avgDecisionSeconds}s · {r.decisionCount} decisions
                    </p>
                  </div>
                ))}
                {anomalies.failOverrideReviewers.map(r => (
                  <div key={r.name} className="rounded border border-red-500/15 bg-red-950/20 px-2 py-1.5">
                    <p className="text-[10px] font-medium text-red-300">{r.name}</p>
                    <p className="text-[10px] text-slate-500 mt-0.5">
                      {r.overrideCount} FAIL overrides
                    </p>
                  </div>
                ))}
              </div>
            </Section>
          )}
        </>
      )}
    </aside>
  );
}

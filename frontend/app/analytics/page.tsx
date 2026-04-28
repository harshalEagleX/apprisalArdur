"use client";
import { useEffect, useState, useCallback } from "react";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

async function api<T>(path: string): Promise<T> {
  const r = await fetch(`${JAVA}${path}`, { credentials: "include" });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

type Days = 7 | 30 | 90;

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, color = "text-blue-400" }: {
  label: string; value: string | number | null; sub?: string; color?: string
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
      <div className={`text-2xl font-bold ${color}`}>{value ?? "—"}</div>
      <div className="text-slate-300 text-sm font-medium mt-1">{label}</div>
      {sub && <div className="text-slate-500 text-xs mt-1">{sub}</div>}
    </div>
  );
}

// ── Section wrapper ────────────────────────────────────────────────────────────
function Section({ title, children, icon }: { title: string; children: React.ReactNode; icon: string }) {
  return (
    <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-6">
      <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <span>{icon}</span>{title}
      </h2>
      {children}
    </div>
  );
}

// ── Progress bar ──────────────────────────────────────────────────────────────
function ProgressBar({ pct, color = "bg-blue-500" }: { pct: number; color?: string }) {
  return (
    <div className="w-full bg-slate-800 rounded-full h-2">
      <div className={`${color} h-2 rounded-full transition-all duration-700`}
           style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
    </div>
  );
}

// ── Trend badge ───────────────────────────────────────────────────────────────
function TrendBadge({ trend }: { trend?: string }) {
  if (!trend) return null;
  const map: Record<string, { label: string; cls: string }> = {
    improving: { label: "↑ Improving", cls: "text-green-400 bg-green-950" },
    declining: { label: "↓ Needs attention", cls: "text-red-400 bg-red-950" },
    stable:    { label: "→ Stable",     cls: "text-slate-300 bg-slate-800" },
  };
  const t = map[trend] ?? map.stable;
  return <span className={`text-xs px-2 py-0.5 rounded font-medium ${t.cls}`}>{t.label}</span>;
}

// ═════════════════════════════════════════════════════════════════════════════
export default function AnalyticsPage() {
  const [days,      setDays]      = useState<Days>(30);
  const [overview,  setOverview]  = useState<Record<string,unknown>>({});
  const [ocr,       setOcr]       = useState<Record<string,unknown>>({});
  const [ml,        setMl]        = useState<Record<string,unknown>>({});
  const [operators, setOperators] = useState<Record<string,unknown>>({});
  const [trend,     setTrend]     = useState<unknown[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState("");

  const load = useCallback(async (d: Days) => {
    setLoading(true); setError("");
    try {
      const [ov, o, m, op, tr] = await Promise.all([
        api<Record<string,unknown>>(`/api/analytics/overview?days=${d}`),
        api<Record<string,unknown>>(`/api/analytics/ocr?days=${d}`),
        api<Record<string,unknown>>(`/api/analytics/ml?days=${d}`),
        api<Record<string,unknown>>(`/api/analytics/operators?days=${d}`),
        api<unknown[]>(`/api/analytics/trend?days=${d}`),
      ]);
      setOverview(ov); setOcr(o); setMl(m); setOperators(op); setTrend(tr);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not load analytics");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(days); }, [days, load]);

  const num = (k: string, src = overview) => Number(src[k] ?? 0);
  const str = (k: string, src = overview) => String(src[k] ?? "—");

  // ── Helpers for nested objects ─────────────────────────────────────────────
  const decisionBreakdown = ml.decisionBreakdown as Record<string,unknown> | undefined;
  const operatorRows      = (operators.operators as unknown[]) ?? [];
  const mvRows            = (ml.modelVersions as unknown[]) ?? [];
  const trendRows         = (trend as Array<Record<string,unknown>>);
  const exMethods         = (ocr.extractionMethods as Array<{method:string;count:number}>) ?? [];

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* ── Top bar ─────────────────────────────────────────────────────────── */}
      <header className="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Analytics Dashboard</h1>
          <p className="text-slate-400 text-sm mt-0.5">Platform performance and operator insights</p>
        </div>
        <div className="flex items-center gap-2">
          {([7,30,90] as Days[]).map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                days === d ? "bg-blue-600 text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700"
              }`}>
              {d}d
            </button>
          ))}
          <a href="/admin" className="ml-4 text-slate-400 hover:text-white text-sm">← Back</a>
        </div>
      </header>

      {error && (
        <div className="m-6 p-4 bg-red-900/30 border border-red-700 rounded-xl text-red-300 text-sm">
          Could not load analytics — please try again or contact support.
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-64 text-slate-500">
          <span className="animate-spin h-6 w-6 border-2 border-blue-500 border-t-transparent rounded-full mr-3" />
          Loading analytics…
        </div>
      ) : (
        <div className="p-6 space-y-6 max-w-7xl mx-auto">

          {/* ── Overview cards ──────────────────────────────────────────────── */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <StatCard label="Files Checked"     value={num("totalFilesProcessed")} color="text-blue-400" />
            <StatCard label="OCR Accuracy"      value={overview.avgOcrAccuracy != null ? `${overview.avgOcrAccuracy}%` : "—"} color="text-emerald-400" sub="average confidence" />
            <StatCard label="Rule Pass Rate"    value={overview.avgRulePassRate != null ? `${overview.avgRulePassRate}%` : "—"} color="text-cyan-400" />
            <StatCard label="Avg Processing"    value={overview.avgProcessingSeconds != null ? `${overview.avgProcessingSeconds}s` : "—"} color="text-amber-400" sub="per file" />
            <StatCard label="Cache Hit Rate"    value={overview.cacheHitRate != null ? `${overview.cacheHitRate}%` : "—"} color="text-purple-400" sub="repeat files" />
            <StatCard label="Pending Review"    value={num("pendingReview")} color="text-rose-400" sub="need your attention" />
          </div>

          {/* ── Main grid ────────────────────────────────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* OCR Insights */}
            <Section title="Document Reading Quality" icon="📄">
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-slate-400 text-sm">Average Accuracy</span>
                  <span className="text-white font-semibold">
                    {ocr.avgAccuracy != null ? `${ocr.avgAccuracy}%` : "—"}
                  </span>
                </div>
                {ocr.avgAccuracy != null && <ProgressBar pct={Number(ocr.avgAccuracy)} color={Number(ocr.avgAccuracy) >= 85 ? "bg-emerald-500" : Number(ocr.avgAccuracy) >= 70 ? "bg-amber-500" : "bg-red-500"} />}

                <div className="text-xs text-slate-500 mt-1">
                  {Number(ocr.avgAccuracy ?? 0) >= 85
                    ? "✓ Documents are being read with high accuracy"
                    : Number(ocr.avgAccuracy ?? 0) >= 70
                    ? "⚠ Some documents may need manual review"
                    : "⚠ Document reading accuracy is low — contact support"}
                </div>

                <div className="flex justify-between items-center pt-2 border-t border-slate-800">
                  <span className="text-slate-400 text-sm">Cached (instant) files</span>
                  <span className="text-purple-400 font-semibold">{String(ocr.cacheHits ?? 0)}</span>
                </div>

                {exMethods.length > 0 && (
                  <div className="pt-2 border-t border-slate-800">
                    <div className="text-slate-500 text-xs mb-2">Reading methods used</div>
                    {exMethods.map(m => (
                      <div key={m.method} className="flex justify-between text-xs text-slate-400 py-0.5">
                        <span className="capitalize">{m.method.replace(/_/g," ") || "Standard"}</span>
                        <span>{m.count} files</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Section>

            {/* ML / Rules Insights */}
            <Section title="Compliance Rule Results" icon="⚖️">
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-slate-400 text-sm">Overall Pass Rate</span>
                  <span className="text-white font-semibold">
                    {ml.avgRulePassRate != null ? `${ml.avgRulePassRate}%` : "—"}
                  </span>
                </div>
                {ml.avgRulePassRate != null && <ProgressBar pct={Number(ml.avgRulePassRate)} color="bg-emerald-500" />}

                {decisionBreakdown && (
                  <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-800">
                    {[
                      { k: "autoPassPct",    label: "Auto passed",   color: "text-emerald-400" },
                      { k: "needsReviewPct", label: "Need review",   color: "text-amber-400" },
                      { k: "autoFailPct",    label: "Auto flagged",  color: "text-rose-400" },
                    ].map(({ k, label, color }) => (
                      <div key={k} className="text-center">
                        <div className={`text-xl font-bold ${color}`}>{decisionBreakdown[k] as number ?? 0}%</div>
                        <div className="text-slate-500 text-xs">{label}</div>
                      </div>
                    ))}
                  </div>
                )}

                {mvRows.length > 0 && (
                  <div className="pt-2 border-t border-slate-800">
                    <div className="text-slate-500 text-xs mb-2">By model version</div>
                    {mvRows.map((v: unknown) => {
                      const row = v as {version:string;avgPassRate:number;filesAnalysed:number};
                      return (
                        <div key={row.version} className="flex justify-between text-xs text-slate-400 py-0.5">
                          <span>Version {row.version}</span>
                          <span>{row.avgPassRate}% pass · {row.filesAnalysed} files</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </Section>

            {/* Operator Performance */}
            <Section title="Team Performance" icon="👥">
              {operatorRows.length === 0 ? (
                <p className="text-slate-500 text-sm">No session data yet for this period.</p>
              ) : (
                <div className="space-y-3">
                  <div className="text-xs text-slate-500 grid grid-cols-4 gap-2 pb-1 border-b border-slate-800">
                    <span>Operator</span><span className="text-right">Hours</span>
                    <span className="text-right">Files</span><span className="text-right">Corrections</span>
                  </div>
                  {(operatorRows as Array<{name:string;activeMinutes:number;filesProcessed:number;corrections:number}>).map(op => (
                    <div key={op.name} className="grid grid-cols-4 gap-2 text-sm">
                      <span className="text-slate-300 truncate">{op.name}</span>
                      <span className="text-right text-slate-400">{(op.activeMinutes / 60).toFixed(1)}h</span>
                      <span className="text-right text-slate-400">{op.filesProcessed}</span>
                      <span className="text-right text-amber-400">{op.corrections}</span>
                    </div>
                  ))}
                </div>
              )}
            </Section>

            {/* Daily Trend */}
            <Section title="Daily Trend" icon="📈">
              {trendRows.length === 0 ? (
                <p className="text-slate-500 text-sm">Not enough data yet to show a trend.</p>
              ) : (
                <div className="space-y-2">
                  <div className="text-xs text-slate-500 grid grid-cols-4 gap-2 pb-1 border-b border-slate-800">
                    <span>Date</span><span className="text-right">Files</span>
                    <span className="text-right">Accuracy</span><span className="text-right">Pass rate</span>
                  </div>
                  <div className="max-h-48 overflow-y-auto space-y-1">
                    {trendRows.map((r) => (
                      <div key={String(r.date)} className="grid grid-cols-4 gap-2 text-xs">
                        <span className="text-slate-400">{String(r.date)}</span>
                        <span className="text-right text-slate-300">{String(r.fileCount)}</span>
                        <span className={`text-right font-medium ${Number(r.ocrAccuracy ?? 0) >= 85 ? "text-emerald-400" : "text-amber-400"}`}>{r.ocrAccuracy as number}%</span>
                        <span className="text-right text-cyan-400">{r.passRate as number}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Section>
          </div>

          {/* ── Guidance banner ──────────────────────────────────────────────── */}
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 flex items-start gap-3">
            <span className="text-2xl mt-0.5">💡</span>
            <div>
              <div className="text-sm font-medium text-slate-200 mb-1">How to read this dashboard</div>
              <div className="text-xs text-slate-400 space-y-1">
                <p>• <strong className="text-slate-300">OCR Accuracy</strong> — how well the system reads documents. Below 70% means some fields may need manual entry.</p>
                <p>• <strong className="text-slate-300">Rule Pass Rate</strong> — percentage of compliance rules automatically satisfied. Lower rates mean more files need reviewer attention.</p>
                <p>• <strong className="text-slate-300">Cache Hit Rate</strong> — files the system recognised instantly (previously processed). High rates mean faster processing.</p>
                <p>• <strong className="text-slate-300">Corrections</strong> — times an operator corrected the system. These improve accuracy over time.</p>
              </div>
            </div>
          </div>

        </div>
      )}
    </div>
  );
}

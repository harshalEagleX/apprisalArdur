"use client";
import { useEffect, useState } from "react";
import { Clock, AlertCircle, CheckCircle2, ChevronRight, RefreshCw } from "lucide-react";
import { type QCResult } from "@/lib/api";
import StatusBadge from "@/components/shared/StatusBadge";
import EmptyState from "@/components/shared/EmptyState";
import { PageSpinner } from "@/components/shared/Spinner";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

export default function ReviewerQueuePage() {
  const [items, setItems]     = useState<QCResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");
  const [refreshing, setRefreshing] = useState(false);

  async function loadQueue(showRefreshSpinner = false) {
    if (showRefreshSpinner) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const r = await fetch(`${JAVA}/api/reviewer/qc/results/pending`, { credentials: "include" });
      if (!r.ok) { setError(`Server responded with ${r.status}`); return; }
      const data: QCResult[] = await r.json();
      setItems(data);
    } catch {
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadQueue(); }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const urgent = items.filter(i => i.failedCount > 0);
  const normal = items.filter(i => i.failedCount === 0);

  return (
    <div className="max-w-4xl mx-auto px-5 py-7">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-white">Verification queue</h1>
          <p className="text-slate-500 text-sm mt-0.5">Appraisal files assigned to you that need a decision</p>
        </div>
        <div className="flex items-center gap-3">
          {items.length > 0 && (
            <span className="text-xs bg-amber-950/60 border border-amber-800/50 text-amber-300 px-2.5 py-1 rounded-full font-medium">
              {items.length} pending
            </span>
          )}
          <button
            onClick={() => loadQueue(true)}
            disabled={refreshing}
            className="h-8 px-3 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 text-slate-400 text-sm flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-5 flex items-start gap-3 p-4 bg-red-950/40 border border-red-800/50 rounded-xl text-red-300 text-sm">
          <AlertCircle size={15} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <PageSpinner label="Loading your queue…" />
      ) : items.length === 0 && !error ? (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl">
          <EmptyState
            icon={CheckCircle2}
            title="Queue is clear"
            description="No files require your review right now. Check back later or refresh."
          />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Urgent — files with failures */}
          {urgent.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-2 px-1">
                <AlertCircle size={12} className="text-red-400" />
                <span className="text-xs font-semibold text-red-400 uppercase tracking-wide">Requires attention — has failures</span>
              </div>
              <QueueList items={urgent} />
            </section>
          )}

          {/* Normal queue */}
          {normal.length > 0 && (
            <section>
              {urgent.length > 0 && (
                <div className="flex items-center gap-2 mb-2 px-1">
                  <Clock size={12} className="text-slate-400" />
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Pending review</span>
                </div>
              )}
              <QueueList items={normal} />
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function QueueList({ items }: { items: QCResult[] }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden divide-y divide-slate-800">
      {items.map(item => {
        const total      = item.totalRules;
        const passRate   = total > 0 ? Math.round((item.passedCount / total) * 100) : 0;
        const hasFailure = item.failedCount > 0;

        return (
          <div key={item.id} className="flex items-center gap-4 px-5 py-4 hover:bg-slate-800/30 transition-colors">
            {/* File icon */}
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${hasFailure ? "bg-red-950/60 border border-red-800/40" : "bg-slate-800 border border-slate-700"}`}>
              <svg className={`w-4 h-4 ${hasFailure ? "text-red-400" : "text-slate-400"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
            </div>

            {/* File info */}
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-slate-200 truncate">{item.batchFile.filename}</div>
              <div className="flex items-center gap-3 mt-1">
                <span className="text-[11px] text-slate-500">
                  Processed {new Date(item.processedAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                </span>
                {item.cacheHit && (
                  <span className="text-[10px] bg-slate-800 border border-slate-700 text-slate-500 px-1.5 py-0.5 rounded font-mono">cached</span>
                )}
              </div>
            </div>

            {/* Rule summary */}
            <div className="hidden sm:flex items-center gap-4 flex-shrink-0">
              <RuleStat label="Pass"   count={item.passedCount}  color="text-green-400" />
              <RuleStat label="Fail"   count={item.failedCount}  color="text-red-400" />
              <RuleStat label="Review" count={item.verifyCount}  color="text-amber-400" />
              <div className="flex flex-col items-end gap-1 w-16">
                <span className="text-[10px] text-slate-600 font-mono">{passRate}% pass</span>
                <div className="w-full h-1 bg-slate-800 rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{
                    width: `${passRate}%`,
                    background: passRate >= 80 ? "#22c55e" : passRate >= 50 ? "#f59e0b" : "#ef4444",
                  }} />
                </div>
              </div>
            </div>

            {/* Decision badge */}
            <div className="hidden md:block flex-shrink-0">
              <StatusBadge status={item.qcDecision} size="xs" />
            </div>

            {/* Action */}
            <a
              href={`/reviewer/verify/${item.id}`}
              className="flex-shrink-0 flex items-center gap-1.5 h-8 px-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors"
            >
              Review <ChevronRight size={13} />
            </a>
          </div>
        );
      })}
    </div>
  );
}

function RuleStat({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <div className="text-center w-10">
      <div className={`text-sm font-bold tabular-nums ${count === 0 ? "text-slate-600" : color}`}>{count}</div>
      <div className="text-[10px] text-slate-600">{label}</div>
    </div>
  );
}

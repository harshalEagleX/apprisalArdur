"use client";
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, XCircle, AlertTriangle, RefreshCw, Shield } from "lucide-react";
import { getPendingOverrides, decideOverride, type PendingOverride } from "@/lib/api";
import { toast } from "@/lib/toast";

function SeverityBadge({ severity }: { severity: string }) {
  const s = (severity ?? "STANDARD").toUpperCase();
  const cls = s === "BLOCKING"
    ? "border-red-500/30 bg-red-950/30 text-red-300"
    : s === "ADVISORY"
    ? "border-amber-500/25 bg-amber-950/20 text-amber-300"
    : "border-white/10 bg-[#0B0F14]/70 text-slate-400";
  return (
    <span className={`inline-flex h-5 items-center rounded border px-1.5 text-[10px] font-semibold uppercase tracking-wide ${cls}`}>
      {s}
    </span>
  );
}

export default function OverridesPage() {
  const [overrides, setOverrides] = useState<PendingOverride[]>([]);
  const [loading, setLoading] = useState(true);
  const [deciding, setDeciding] = useState<Set<number>>(new Set());
  const [comments, setComments] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getPendingOverrides();
      setOverrides(data);
    } catch {
      toast.error("Failed to load pending overrides");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function decide(ruleResultId: number, approve: boolean) {
    setDeciding(prev => new Set(prev).add(ruleResultId));
    try {
      await decideOverride(ruleResultId, approve, comments[ruleResultId]);
      toast.success(approve ? "Override approved — reviewer notified" : "Override rejected — reviewer notified");
      setOverrides(prev => prev.filter(o => o.ruleResultId !== ruleResultId));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Decision failed");
    } finally {
      setDeciding(prev => { const n = new Set(prev); n.delete(ruleResultId); return n; });
    }
  }

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-8">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            <Shield size={14} /> Admin · Override Queue
          </div>
          <h1 className="mt-1 text-2xl font-semibold text-white">Pending Overrides</h1>
          <p className="mt-1 text-sm text-slate-500">
            Rules flagged by reviewers for second-approval. Approve to accept the FAIL override,
            or reject to send back for reviewer reconsideration.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex h-9 items-center gap-1.5 rounded-md border border-white/10 px-3 text-sm text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white disabled:opacity-40"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="rounded-lg border border-white/10 bg-[#11161C] p-12 text-center text-slate-500">
          Loading overrides…
        </div>
      ) : overrides.length === 0 ? (
        <div className="rounded-lg border border-white/10 bg-[#11161C] p-12 text-center">
          <CheckCircle2 size={32} className="mx-auto mb-3 text-green-400/70" />
          <div className="text-sm font-medium text-slate-300">No pending overrides</div>
          <div className="mt-1 text-xs text-slate-600">All reviewer FAIL escalations have been resolved.</div>
        </div>
      ) : (
        <div className="space-y-3">
          {overrides.map(o => (
            <div
              key={o.ruleResultId}
              className="rounded-lg border border-amber-500/20 bg-amber-950/10 p-4 shadow-[0_4px_16px_rgba(0,0,0,0.15)]"
            >
              <div className="flex flex-wrap items-start gap-3">
                <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-400" />
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-bold text-amber-300">{o.ruleId}</span>
                    <SeverityBadge severity={o.severity} />
                    <span className="text-xs text-slate-400">{o.ruleName}</span>
                  </div>
                  <p className="text-sm text-slate-300">{o.message}</p>
                  {o.reviewerComment && (
                    <p className="text-xs italic text-slate-500">
                      Reviewer note: "{o.reviewerComment}"
                    </p>
                  )}
                  <div className="flex flex-wrap gap-3 text-[11px] text-slate-600">
                    {o.filename && <span>File: <span className="text-slate-400">{o.filename}</span></span>}
                    {o.parentBatchId && <span>Batch: <span className="font-mono text-slate-400">{o.parentBatchId}</span></span>}
                    {o.overrideRequestedBy && <span>Requested by: <span className="text-slate-400">{o.overrideRequestedBy}</span></span>}
                    {o.overrideRequestedAt && <span>At: <span className="text-slate-400">{new Date(o.overrideRequestedAt).toLocaleString()}</span></span>}
                  </div>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <input
                  type="text"
                  value={comments[o.ruleResultId] ?? ""}
                  onChange={e => setComments(prev => ({ ...prev, [o.ruleResultId]: e.target.value }))}
                  placeholder="Optional admin note…"
                  className="h-8 flex-1 rounded-md border border-white/10 bg-[#0B0F14]/70 px-3 text-xs text-white placeholder-slate-600 focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30"
                />
                <button
                  onClick={() => decide(o.ruleResultId, true)}
                  disabled={deciding.has(o.ruleResultId)}
                  className="inline-flex h-8 items-center gap-1.5 rounded-md border border-green-500/30 bg-green-950/30 px-3 text-xs font-medium text-green-300 transition-colors hover:bg-green-950/60 disabled:opacity-40"
                >
                  <CheckCircle2 size={13} /> Approve Override
                </button>
                <button
                  onClick={() => decide(o.ruleResultId, false)}
                  disabled={deciding.has(o.ruleResultId)}
                  className="inline-flex h-8 items-center gap-1.5 rounded-md border border-red-500/25 bg-red-950/30 px-3 text-xs font-medium text-red-300 transition-colors hover:bg-red-950/60 disabled:opacity-40"
                >
                  <XCircle size={13} /> Reject Override
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}

"use client";
import { useEffect, useState } from "react";
import { Activity, ChevronDown, X } from "lucide-react";
import { subscribeJobs, removeJob, type ActiveJob } from "@/lib/jobs";

const LS_KEY = "activityMonitor.expanded";

/**
 * Background-activity monitor. Redesigned to NEVER overlap or block content:
 * - Defaults to a small docked PILL (tiny footprint) — the full panel is opt-in,
 *   not a permanent floating card sitting over the workspace.
 * - When expanded, the panel is height-bounded (max 70vh) and scrolls, so it can
 *   never grow to cover the screen.
 * - Minimize returns to the pill; the choice is remembered across navigations.
 * Same theme/colors as before — only behavior and footprint changed.
 */
export default function ActivityMonitor() {
  const [jobs, setJobs]       = useState<ActiveJob[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [now, setNow]         = useState(() => Date.now());

  // Restore the user's last pill/panel choice so it isn't intrusive on every load.
  useEffect(() => {
    try { setExpanded(localStorage.getItem(LS_KEY) === "1"); } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    try { localStorage.setItem(LS_KEY, expanded ? "1" : "0"); } catch { /* ignore */ }
  }, [expanded]);

  useEffect(() => {
    const unsub = subscribeJobs(setJobs);
    return () => { unsub(); };
  }, []);

  useEffect(() => {
    if (jobs.length === 0) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [jobs.length]);

  if (jobs.length === 0) return null;

  // Aggregate progress for the collapsed pill so the user gets at-a-glance status
  // without having to open the panel.
  const aggPct = Math.round(
    jobs.reduce((sum, j) => {
      const fallback = j.total > 0 ? (j.current / j.total) * 100 : 0;
      return sum + Math.max(0, Math.min(100, j.smoothedPercent ?? fallback));
    }, 0) / jobs.length
  );

  // Collapsed: a compact pill in the bottom-right. Small enough that it never blocks
  // the workspace; click to open the full panel on demand.
  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="foundation-fade-in fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full border border-white/10 bg-[#11161C]/95 px-3 py-2 shadow-[0_12px_32px_rgba(0,0,0,0.40)] backdrop-blur transition-colors hover:bg-[#161B22]"
        title="Show background activity"
      >
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-slate-400/60" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-slate-300" />
        </span>
        <Activity size={13} className="text-slate-300" />
        <span className="text-[11px] font-semibold text-slate-200">{jobs.length} active</span>
        <span className="font-mono text-[10px] text-slate-500">{aggPct}%</span>
      </button>
    );
  }

  return (
    <div className="foundation-fade-in fixed bottom-4 right-4 z-40 flex max-h-[min(70vh,30rem)] w-[min(20rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-lg border border-white/10 bg-[#11161C] shadow-[0_20px_55px_rgba(0,0,0,0.42)]">
      {/* Header */}
      <div className="flex flex-shrink-0 items-center justify-between border-b border-white/10 bg-[#11161C] px-3 py-2.5">
        <div className="flex items-center gap-2">
          <Activity size={13} className="text-slate-300" />
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-300">
            Background activity
          </span>
          <span className="rounded-full border border-slate-500/25 bg-slate-950/35 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-slate-100">
            {jobs.length}
          </span>
        </div>
        <button
          onClick={() => setExpanded(false)}
          className="p-0.5 text-slate-500 transition-colors hover:text-slate-300"
          title="Minimize to pill"
        >
          <ChevronDown size={14} />
        </button>
      </div>

      {/* Jobs — scrolls inside the bounded panel so it can never cover the screen */}
      <div className="divide-y divide-white/10 overflow-y-auto">
        {jobs.map(job => {
          const fallbackPct = job.total > 0
            ? Math.max(0, Math.min(100, Math.round((job.current / job.total) * 100)))
            : 0;
          // Prefer the smoothed percent (current+subPercent) computed on the
          // server / poll loop so the bar moves while a single file's Python
          // pipeline progresses through OCR → extraction → LLM → rules.
          const pct = job.smoothedPercent ?? fallbackPct;
          const elapsed = Math.max(0, Math.round((now - job.startedAt) / 1000));
          const subLabel = job.subStage ? job.subStage.replace(/_/g, " ") : null;
          return (
            <div key={job.id} className="px-3 py-3">
              <div className="mb-2 flex items-start justify-between">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium text-slate-200">{job.label}</div>
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    {job.current} / {job.total} {job.unitLabel ?? "files"} &middot; {elapsed}s elapsed
                  </div>
                  {job.detail && (
                    <div className="mt-0.5 truncate text-[10px] text-slate-600">
                      {job.detail}
                    </div>
                  )}
                  {subLabel && (
                    <div className="mt-0.5 truncate text-[10px] text-slate-200" title={job.subMessage ?? subLabel}>
                      {subLabel}{job.subMessage ? ` — ${job.subMessage}` : ""}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => removeJob(job.id)}
                  className="ml-2 flex-shrink-0 text-slate-600 transition-colors hover:text-slate-400"
                  title="Dismiss"
                >
                  <X size={12} />
                </button>
              </div>
              {/* Progress bar */}
              <div className="h-1.5 overflow-hidden rounded-full bg-[#0B0F14]">
                <div
                  className="h-full rounded-full bg-slate-500 transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className="mt-1 flex justify-between">
                <span className="truncate pr-2 text-[10px] text-slate-500">
                  {job.message || (pct < 100 ? "Processing…" : "Finalising…")}
                </span>
                <span className="font-mono text-[10px] text-slate-500">{pct}%</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

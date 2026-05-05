"use client";
import { useEffect, useState } from "react";
import { Activity, ChevronDown, ChevronUp, X } from "lucide-react";
import { subscribeJobs, removeJob, type ActiveJob } from "@/lib/jobs";

export default function ActivityMonitor() {
  const [jobs, setJobs]           = useState<ActiveJob[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const [now, setNow]             = useState(() => Date.now());

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

  return (
    <div className="foundation-fade-in fixed bottom-4 right-4 z-40 w-[min(20rem,calc(100vw-2rem))] overflow-hidden rounded-lg border border-white/10 bg-[#11161C] shadow-[0_20px_55px_rgba(0,0,0,0.42)]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 bg-[#11161C] px-3 py-2.5">
        <div className="flex items-center gap-2">
          <Activity size={13} className="text-slate-300" />
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-300">
            Background activity
          </span>
          <span className="rounded-full border border-slate-500/25 bg-slate-950/35 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-slate-100">
            {jobs.length}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setCollapsed(c => !c)}
            className="p-0.5 text-slate-500 transition-colors hover:text-slate-300"
            title={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {/* Jobs */}
      {!collapsed && (
        <div className="divide-y divide-white/10">
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
                  <div className="flex-1 min-w-0">
                    <div className="truncate text-xs font-medium text-slate-200">{job.label}</div>
                    <div className="mt-0.5 text-[11px] text-slate-500">
                      {job.current} / {job.total} {job.unitLabel ?? "files"} &middot; {elapsed}s elapsed
                    </div>
                    {job.detail && (
                      <div className="mt-0.5 truncate text-[10px] text-slate-600">
                        {job.detail}
                      </div>
                    )}
                    {job.modelLabel && (
                      <div className="mt-0.5 truncate text-[10px] text-slate-300">
                        {job.modelLabel}
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
                  <span className="text-[10px] text-slate-500 font-mono">{pct}%</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

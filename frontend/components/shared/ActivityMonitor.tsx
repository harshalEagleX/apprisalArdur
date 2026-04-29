"use client";
import { useEffect, useState } from "react";
import { Activity, ChevronDown, ChevronUp, X } from "lucide-react";
import { subscribeJobs, removeJob, type ActiveJob } from "@/lib/jobs";

export default function ActivityMonitor() {
  const [jobs, setJobs]           = useState<ActiveJob[]>([]);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const unsub = subscribeJobs(setJobs);
    return () => { unsub(); };
  }, []);

  if (jobs.length === 0) return null;

  return (
    <div className="fixed bottom-4 left-4 z-40 w-80 rounded-xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-slate-800 bg-slate-900">
        <div className="flex items-center gap-2">
          <Activity size={13} className="text-blue-400 animate-pulse" />
          <span className="text-xs font-semibold text-slate-300 uppercase tracking-wide">
            Background activity
          </span>
          <span className="bg-blue-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none">
            {jobs.length}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setCollapsed(c => !c)}
            className="text-slate-500 hover:text-slate-300 transition-colors p-0.5"
            title={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {/* Jobs */}
      {!collapsed && (
        <div className="divide-y divide-slate-800">
          {jobs.map(job => {
            const pct = job.total > 0 ? Math.round((job.current / job.total) * 100) : 0;
            const elapsed = Math.round((Date.now() - job.startedAt) / 1000);
            return (
              <div key={job.id} className="px-3 py-3">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-slate-200 truncate">{job.label}</div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      {job.current} / {job.total} files &middot; {elapsed}s elapsed
                    </div>
                  </div>
                  <button
                    onClick={() => removeJob(job.id)}
                    className="text-slate-600 hover:text-slate-400 ml-2 flex-shrink-0 transition-colors"
                    title="Dismiss"
                  >
                    <X size={12} />
                  </button>
                </div>
                {/* Progress bar */}
                <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all duration-500"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="flex justify-between mt-1">
                  <span className="text-[10px] text-slate-600">
                    {pct < 100 ? "Processing…" : "Finalising…"}
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

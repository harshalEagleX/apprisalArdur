"use client";
import { useEffect, useState } from "react";
import { type QCResult } from "@/lib/api";
import StatusBadge from "@/components/shared/StatusBadge";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

export default function ReviewerQueuePage() {
  const [items, setItems]     = useState<QCResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const qRes = await fetch(`${JAVA}/api/reviewer/qc/results/pending`, { credentials: "include" });
        if (!qRes.ok) { setError(`Failed to load queue (HTTP ${qRes.status})`); return; }
        const data: QCResult[] = await qRes.json();
        setItems(data);
      } catch {
        setError("Could not connect to server.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  return (
    <main className="max-w-4xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Verification Queue</h1>
          <p className="text-slate-400 text-sm mt-0.5">Files assigned to you that need human review</p>
        </div>
        <span className="bg-amber-900/60 text-amber-300 px-3 py-1 rounded-full text-sm font-medium">
          {items.length} pending
        </span>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-900/30 border border-red-700 rounded-xl text-red-300 text-sm">{error}</div>
      )}

      {loading ? (
        <div className="text-center py-12 text-slate-500">
          <span className="inline-block animate-spin h-6 w-6 border-2 border-blue-500 border-t-transparent rounded-full mr-2" />
          Loading queue…
        </div>
      ) : items.length === 0 && !error ? (
        <div className="text-center py-16">
          <div className="text-5xl mb-3">✅</div>
          <h3 className="text-lg font-semibold text-green-400">All caught up!</h3>
          <p className="text-slate-400 text-sm mt-1">No files require your review right now.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map(item => (
            <div key={item.id}
              className="bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-xl p-4 flex items-center gap-4 transition-colors">
              <div className="text-2xl flex-shrink-0">📄</div>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-slate-200 truncate">{item.batchFile.filename}</div>
                <div className="text-xs text-slate-500 mt-0.5">
                  Processed {new Date(item.processedAt).toLocaleString()}
                  {item.cacheHit && (
                    <span className="ml-2 bg-blue-900/60 text-blue-300 px-1.5 py-0.5 rounded text-[10px]">Cached</span>
                  )}
                </div>
              </div>

              {/* Rule counts */}
              <div className="flex gap-4 text-center flex-shrink-0">
                {[
                  { label: "Pass",   count: item.passedCount,  color: "text-green-400" },
                  { label: "Fail",   count: item.failedCount,  color: "text-red-400" },
                  { label: "Review", count: item.verifyCount,  color: "text-amber-400" },
                  { label: "Total",  count: item.totalRules,   color: "text-slate-300" },
                ].map(s => (
                  <div key={s.label} className="min-w-[40px]">
                    <div className={`text-base font-bold ${s.color}`}>{s.count}</div>
                    <div className="text-[11px] text-slate-600">{s.label}</div>
                  </div>
                ))}
              </div>

              <div className="flex-shrink-0">
                <StatusBadge status={item.qcDecision.replace("_", " ")} />
              </div>

              <a
                href={`/reviewer/verify/${item.id}`}
                className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg font-medium transition-colors flex-shrink-0"
              >
                Verify →
              </a>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}

"use client";
import { useEffect, useState } from "react";
import { getQCResults, type QCResult } from "@/lib/api";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

export default function ReviewerQueuePage() {
  const [items, setItems]     = useState<QCResult[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // IMPL FIX: use reviewer-scoped endpoint, not /api/admin/batches
    // This respects reviewer's assigned batches and doesn't require ADMIN role
    const loadQueue = async () => {
      try {
        // Get batches assigned to this reviewer via reviewer API
        const bRes = await fetch(`${JAVA}/api/reviewer/dashboard`, { credentials: "include" });
        if (!bRes.ok) {
          if (bRes.status === 401 || bRes.status === 403) window.location.href = "/login";
          return;
        }

        // Use the reviewer-accessible batch list (from security-scoped endpoint)
        const qRes = await fetch(`${JAVA}/api/qc/results/pending`, { credentials: "include" });
        if (qRes.ok) {
          const data: QCResult[] = await qRes.json();
          setItems(data.filter(r => r.qcDecision === "TO_VERIFY" && !r.finalDecision));
          return;
        }

        // Fallback: admin or reviewer with broader access
        const aRes = await fetch(`${JAVA}/api/client/batches?size=100`, { credentials: "include" });
        if (!aRes.ok) return;
        const page = await aRes.json();
        const batches = (page.content ?? []) as { id: number; status: string }[];

        const allResults: QCResult[] = [];
        for (const batch of batches) {
          if (!["REVIEW_PENDING","IN_REVIEW"].includes(batch.status)) continue;
          const res = await getQCResults(batch.id);
          allResults.push(...res.filter((r: QCResult) => r.qcDecision === "TO_VERIFY" && !r.finalDecision));
        }
        setItems(allResults);
      } catch (e) {
        console.error("Failed to load queue:", e);
      } finally {
        setLoading(false);
      }
    };
    loadQueue();
  }, []);

  const badge = (decision: string) => {
    if (decision === "AUTO_PASS") return "bg-green-900 text-green-300";
    if (decision === "TO_VERIFY") return "bg-amber-900 text-amber-300";
    return "bg-red-900 text-red-300";
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <nav className="bg-slate-900 border-b border-slate-800 px-6 py-3 flex items-center gap-4">
        <div className="w-8 h-8 bg-blue-600 rounded flex items-center justify-center font-bold text-sm">A</div>
        <span className="font-semibold">Ardur Appraisal</span>
        <span className="text-slate-400">/ Reviewer</span>
        <div className="ml-auto flex gap-3">
          <a href="/reviewer/queue" className="text-blue-400 text-sm">Queue</a>
          <a href="/login" className="text-slate-400 text-sm hover:text-white">Logout</a>
        </div>
      </nav>

      <main className="max-w-5xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Verification Queue</h1>
            <p className="text-slate-400 text-sm">Files requiring human review</p>
          </div>
          <span className="bg-amber-900 text-amber-300 px-3 py-1 rounded-full text-sm font-medium">
            {items.length} pending
          </span>
        </div>

        {loading ? (
          <div className="text-center py-12 text-slate-500">Loading queue…</div>
        ) : items.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-4xl mb-3">✅</div>
            <h3 className="text-lg font-semibold text-green-400">All caught up!</h3>
            <p className="text-slate-400 text-sm mt-1">No files require verification right now.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map(item => (
              <div key={item.id} className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
                <div className="text-red-400 text-2xl flex-shrink-0">📄</div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{item.batchFile.filename}</div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    Processed {new Date(item.processedAt).toLocaleString()}
                    {item.cacheHit && <span className="ml-2 bg-blue-900 text-blue-300 px-1.5 py-0.5 rounded">Cached</span>}
                  </div>
                </div>
                <div className="flex gap-3 text-center flex-shrink-0">
                  {[
                    { label: "Pass",   count: item.passedCount,  color: "text-green-400" },
                    { label: "Fail",   count: item.failedCount,  color: "text-red-400" },
                    { label: "Review", count: item.verifyCount,  color: "text-amber-400" },
                  ].map(s => (
                    <div key={s.label}>
                      <div className={`font-bold ${s.color}`}>{s.count}</div>
                      <div className="text-xs text-slate-500">{s.label}</div>
                    </div>
                  ))}
                  <div>
                    <div className="font-bold text-slate-300">{item.totalRules}</div>
                    <div className="text-xs text-slate-500">Total</div>
                  </div>
                </div>
                <span className={`text-xs px-2 py-1 rounded font-medium flex-shrink-0 ${badge(item.qcDecision)}`}>
                  {item.qcDecision.replace("_"," ")}
                </span>
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
    </div>
  );
}

"use client";

import { useEffect, useState, useCallback } from "react";

// QC reports are served by the Python OCR service. (Demo page — calls Python
// directly; a production build would proxy through the Java backend.)
const PY = process.env.NEXT_PUBLIC_PYTHON_URL ?? "http://localhost:5001";

type Status = "PASS" | "FAIL" | "VERIFY" | "HOLD" | "NOT_APPLICABLE" | "SKIPPED";

type Evidence = {
  document: string;
  value: string | null;
  confidence: number;
  page: number | null;
};
type Finding = {
  rule_id: string;
  checklist_num: string | null;
  section: string;
  status: Status;
  message: string;
  fields: string[];
  confidence: number;
  evidence: Evidence[];
};
type Report = {
  transaction_id: string;
  overall: Status;
  counts: Record<string, number>;
  exception_count: number;
  rule_count: number;
  sections: Record<string, Finding[]>;
};
type TxnSummary = {
  transaction_id: string;
  overall: Status;
  exception_count: number;
  rule_count: number;
};

const STATUS: Record<Status, { dot: string; text: string; label: string }> = {
  PASS: { dot: "bg-emerald-500", text: "text-emerald-400", label: "Pass" },
  FAIL: { dot: "bg-rose-500", text: "text-rose-400", label: "Fail" },
  VERIFY: { dot: "bg-amber-500", text: "text-amber-400", label: "Verify" },
  HOLD: { dot: "bg-fuchsia-500", text: "text-fuchsia-400", label: "Hold" },
  NOT_APPLICABLE: { dot: "bg-slate-600", text: "text-slate-500", label: "N/A" },
  SKIPPED: { dot: "bg-slate-700", text: "text-slate-500", label: "Skipped" },
};

async function api<T>(path: string): Promise<T> {
  const r = await fetch(`${PY}${path}`);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

function StatusPill({ status }: { status: Status }) {
  const s = STATUS[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border border-white/10 px-2 py-0.5 text-xs font-medium ${s.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

function CountBar({ counts }: { counts: Record<string, number> }) {
  const order: Status[] = ["PASS", "VERIFY", "FAIL", "HOLD", "NOT_APPLICABLE", "SKIPPED"];
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      {order.filter((k) => counts[k]).map((k) => (
        <span key={k} className={`tabular-nums ${STATUS[k].text}`}>
          {STATUS[k].label} {counts[k]}
        </span>
      ))}
    </div>
  );
}

function FindingRow({ f }: { f: Finding }) {
  const isException = f.status === "FAIL" || f.status === "VERIFY" || f.status === "HOLD";
  return (
    <div className={`rounded-md border px-3 py-2 ${isException ? "border-white/10 bg-[#11161C]/80" : "border-transparent"}`}>
      <div className="flex items-start gap-3">
        <StatusPill status={f.status} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-slate-200">
            {f.rule_id}
            {f.checklist_num && <span className="ml-2 text-xs text-slate-500">#{f.checklist_num}</span>}
          </div>
          {isException && f.message && (
            <div className="mt-0.5 text-sm text-slate-400">{f.message}</div>
          )}
          {f.evidence.filter((e) => e.value).length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-2">
              {f.evidence.filter((e) => e.value).map((e, i) => (
                <span key={i} className="rounded border border-white/10 bg-black/30 px-2 py-0.5 text-xs text-slate-400">
                  <span className="text-slate-500">{e.document}:</span>{" "}
                  <span className="text-slate-300">{e.value}</span>
                  <span className="ml-1 text-slate-600">
                    ({(e.confidence * 100).toFixed(0)}%{e.page ? `, p${e.page}` : ""})
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function QCReviewPage() {
  const [txns, setTxns] = useState<TxnSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPasses, setShowPasses] = useState(false);

  useEffect(() => {
    api<TxnSummary[]>("/qc/transactions")
      .then((d) => { setTxns(d); if (d.length) setSelected(d[0].transaction_id); })
      .catch(() => setError("Could not load transactions. Is the OCR service running on :5001?"));
  }, []);

  const load = useCallback((tid: string) => {
    setLoading(true); setError(null);
    api<Report>(`/qc/report/${encodeURIComponent(tid)}`)
      .then(setReport)
      .catch(() => setError("Could not load this report."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { if (selected) load(selected); }, [selected, load]);

  return (
    <div className="min-h-screen bg-[#0B0E13] text-slate-200">
      <div className="mx-auto flex max-w-7xl gap-6 p-6">
        {/* Transaction list */}
        <aside className="w-72 shrink-0">
          <h1 className="mb-1 text-lg font-semibold">QC Review</h1>
          <p className="mb-4 text-xs text-slate-500">{txns.length} transactions</p>
          <div className="space-y-1.5">
            {txns.map((t) => (
              <button
                key={t.transaction_id}
                onClick={() => setSelected(t.transaction_id)}
                className={`block w-full rounded-md border px-3 py-2 text-left transition-colors ${
                  selected === t.transaction_id
                    ? "border-slate-500/40 bg-[#161B22]"
                    : "border-white/10 bg-[#11161C]/70 hover:bg-[#161B22]"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm text-slate-300">{t.transaction_id}</span>
                  <StatusPill status={t.overall} />
                </div>
                <div className="mt-0.5 text-xs text-slate-500">
                  {t.exception_count} exceptions / {t.rule_count} rules
                </div>
              </button>
            ))}
          </div>
        </aside>

        {/* Report */}
        <main className="min-w-0 flex-1">
          {error && <div className="rounded-md border border-rose-500/30 bg-rose-950/30 px-4 py-3 text-sm text-rose-300">{error}</div>}
          {loading && <div className="text-sm text-slate-500">Loading…</div>}
          {report && !loading && (
            <>
              <div className="mb-4 flex items-center justify-between rounded-lg border border-white/10 bg-[#11161C]/80 px-5 py-4">
                <div>
                  <div className="text-sm text-slate-500">{report.transaction_id}</div>
                  <div className="mt-1 flex items-center gap-3">
                    <span className="text-xl font-semibold">Overall</span>
                    <StatusPill status={report.overall} />
                  </div>
                </div>
                <div className="text-right">
                  <CountBar counts={report.counts} />
                  <div className="mt-1 text-xs text-slate-500">
                    {report.exception_count} of {report.rule_count} need attention
                  </div>
                </div>
              </div>

              <label className="mb-3 flex cursor-pointer items-center gap-2 text-xs text-slate-500">
                <input type="checkbox" checked={showPasses} onChange={(e) => setShowPasses(e.target.checked)} />
                Show passed / not-applicable rules
              </label>

              <div className="space-y-5">
                {Object.entries(report.sections).map(([section, findings]) => {
                  const visible = findings.filter(
                    (f) => showPasses || ["FAIL", "VERIFY", "HOLD"].includes(f.status)
                  );
                  if (!visible.length) return null;
                  return (
                    <section key={section}>
                      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
                        {section.replace(/_/g, " ")}
                      </h2>
                      <div className="space-y-1.5">
                        {visible.map((f, i) => <FindingRow key={`${f.rule_id}-${i}`} f={f} />)}
                      </div>
                    </section>
                  );
                })}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

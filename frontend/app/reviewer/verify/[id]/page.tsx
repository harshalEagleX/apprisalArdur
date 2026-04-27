"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { getQCRules, getQCProgress, saveDecision, getPdfUrl, type QCRuleResult } from "@/lib/api";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

const STATUS_STYLE: Record<string, string> = {
  pass:         "bg-green-900/30 border-green-700 text-green-300",
  fail:         "bg-red-900/30 border-red-700 text-red-300",
  verify:       "bg-amber-900/30 border-amber-700 text-amber-300",
  warning:      "bg-orange-900/30 border-orange-700 text-orange-300",
  system_error: "bg-purple-900/30 border-purple-700 text-purple-300",
  skipped:      "bg-slate-800 border-slate-700 text-slate-400",
};

const SEV_BADGE: Record<string, string> = {
  BLOCKING: "bg-red-900 text-red-200",
  STANDARD: "bg-blue-900 text-blue-200",
  ADVISORY: "bg-slate-700 text-slate-300",
};

type Decision = "ACCEPT" | "REJECT";
type Filter = "all" | "fail" | "verify" | "pass" | "warning";

export default function VerifyFilePage() {
  const { id } = useParams<{ id: string }>();
  const qcResultId = Number(id);

  const [rules, setRules]       = useState<QCRuleResult[]>([]);
  const [loading, setLoading]   = useState(true);
  const [filter, setFilter]     = useState<Filter>("all");
  const [decisions, setDecisions] = useState<Record<number, Decision>>({});
  const [comments, setComments]   = useState<Record<number, string>>({});
  const [saving, setSaving]       = useState<number | null>(null);
  const [saved, setSaved]         = useState<Set<number>>(new Set());
  const [progress, setProgress]   = useState<{ pending: number; canSubmit: boolean } | null>(null);
  const [pdfFileId, setPdfFileId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const loadRules = useCallback(async () => {
    try {
      setLoading(true);
      const [rulesData, prog] = await Promise.all([
        getQCRules(qcResultId),
        getQCProgress(qcResultId),
      ]);
      setRules(rulesData);
      setProgress(prog);

      // Pre-populate existing decisions
      const dec: Record<number, Decision> = {};
      const com: Record<number, string>   = {};
      for (const r of rulesData) {
        if (r.reviewerVerified === true)  dec[r.id] = "ACCEPT";
        if (r.reviewerVerified === false) dec[r.id] = "REJECT";
        if (r.reviewerComment) com[r.id] = r.reviewerComment;
      }
      setDecisions(dec);
      setComments(com);
    } finally {
      setLoading(false);
    }
  }, [qcResultId]);

  // Load the PDF file id from QC result
  useEffect(() => {
    fetch(`${JAVA}/api/qc/file/${qcResultId}`, { credentials: "include" })
      .then(r => r.json())
      .then((d: { batchFile?: { id: number } }) => { if (d?.batchFile?.id) setPdfFileId(d.batchFile.id); })
      .catch(() => null);
  }, [qcResultId]);

  useEffect(() => { loadRules(); }, [loadRules]);

  async function handleDecision(ruleId: number, decision: Decision) {
    setDecisions(prev => ({ ...prev, [ruleId]: decision }));
    setSaving(ruleId);
    try {
      await saveDecision(ruleId, decision, comments[ruleId]);
      setSaved(prev => new Set(prev).add(ruleId));
      const prog = await getQCProgress(qcResultId);
      setProgress(prog);
    } catch {
      // revert on error
      setDecisions(prev => { const n = {...prev}; delete n[ruleId]; return n; });
    } finally {
      setSaving(null);
    }
  }

  async function handleSubmit() {
    setSubmitting(true);
    try {
      const form = new FormData();
      for (const [ruleId, dec] of Object.entries(decisions)) {
        form.append(`decision_${ruleId}`, dec.toLowerCase());
        if (comments[Number(ruleId)]) form.append(`comment_${ruleId}`, comments[Number(ruleId)]);
      }
      await fetch(`${JAVA}/reviewer/verify/${qcResultId}`, {
        method: "POST", credentials: "include", body: form,
      });
      window.location.href = "/reviewer/queue";
    } finally {
      setSubmitting(false);
    }
  }

  const filtered = rules.filter(r => {
    if (filter === "all")     return true;
    if (filter === "fail")    return r.status === "fail";
    if (filter === "verify")  return r.status === "verify" || r.status === "warning";
    if (filter === "pass")    return r.status === "pass";
    if (filter === "warning") return r.status === "warning";
    return true;
  });

  const counts = {
    total:   rules.length,
    pass:    rules.filter(r => r.status === "pass").length,
    fail:    rules.filter(r => r.status === "fail").length,
    verify:  rules.filter(r => r.status === "verify" || r.status === "warning").length,
  };

  return (
    <div className="h-screen flex flex-col bg-slate-950 text-white">
      {/* Top bar */}
      <header className="flex items-center gap-4 px-4 py-2.5 bg-slate-900 border-b border-slate-800 flex-shrink-0">
        <a href="/reviewer/queue" className="text-slate-400 hover:text-white text-sm flex items-center gap-1">
          ← Queue
        </a>
        <div className="flex-1 flex items-center gap-2">
          <span className="text-red-400">📄</span>
          <span className="text-sm font-medium">QC Result #{qcResultId}</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="bg-green-900 text-green-300 px-2 py-0.5 rounded">{counts.pass} Pass</span>
          <span className="bg-red-900 text-red-300 px-2 py-0.5 rounded">{counts.fail} Fail</span>
          <span className="bg-amber-900 text-amber-300 px-2 py-0.5 rounded">{counts.verify} Review</span>
        </div>
        <button
          onClick={handleSubmit}
          disabled={!progress?.canSubmit || submitting}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm px-4 py-1.5 rounded-lg font-medium transition-colors"
        >
          {submitting ? "Submitting…" : `Submit Review${progress?.pending ? ` (${progress.pending} left)` : ""}`}
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left: PDF viewer */}
        <div className="w-[55%] flex-shrink-0 border-r border-slate-800 flex flex-col">
          <div className="px-3 py-2 bg-slate-900 border-b border-slate-800 text-xs text-slate-400 flex items-center gap-2">
            <span className="text-red-400">📄</span> Appraisal Document
          </div>
          {pdfFileId ? (
            <iframe
              src={getPdfUrl(pdfFileId)}
              className="flex-1 w-full"
              title="PDF Viewer"
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
              Loading document…
            </div>
          )}
        </div>

        {/* Right: QC panel */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Filter bar */}
          <div className="flex items-center gap-1 px-3 py-2 bg-slate-900 border-b border-slate-800 flex-wrap">
            {(["all","fail","verify","pass"] as Filter[]).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors ${
                  filter === f ? "bg-blue-600 text-white" : "bg-slate-800 text-slate-400 hover:text-white"
                }`}>
                {f === "all" ? `All (${counts.total})` :
                 f === "fail" ? `❌ Fail (${counts.fail})` :
                 f === "verify" ? `⚠️ Review (${counts.verify})` :
                 `✅ Pass (${counts.pass})`}
              </button>
            ))}
          </div>

          {/* Rules list */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {loading ? (
              <div className="text-center text-slate-500 py-8">Loading rules…</div>
            ) : filtered.length === 0 ? (
              <div className="text-center text-slate-500 py-8">No rules match this filter.</div>
            ) : (
              filtered.map(rule => (
                <RuleCard
                  key={rule.id}
                  rule={rule}
                  decision={decisions[rule.id]}
                  comment={comments[rule.id] ?? ""}
                  saving={saving === rule.id}
                  savedNow={saved.has(rule.id)}
                  onDecision={d => handleDecision(rule.id, d)}
                  onComment={c => setComments(prev => ({ ...prev, [rule.id]: c }))}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function RuleCard({
  rule, decision, comment, saving, savedNow, onDecision, onComment,
}: {
  rule: QCRuleResult;
  decision?: Decision;
  comment: string;
  saving: boolean;
  savedNow: boolean;
  onDecision: (d: Decision) => void;
  onComment: (c: string) => void;
}) {
  const [expanded, setExpanded] = useState(rule.status === "fail" || rule.status === "verify");
  const style = STATUS_STYLE[rule.status] ?? STATUS_STYLE.skipped;
  const sev   = rule.severity ?? "STANDARD";

  return (
    <div className={`rounded-lg border p-3 ${style}`}>
      <div className="flex items-start gap-2">
        <span className="font-mono text-xs bg-slate-800/60 px-1.5 py-0.5 rounded text-slate-300 flex-shrink-0">
          {rule.ruleId}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-sm font-medium">{rule.ruleName}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${SEV_BADGE[sev] ?? SEV_BADGE.STANDARD}`}>
              {sev}
            </span>
            <span className={`text-xs px-1.5 py-0.5 rounded uppercase font-medium ${
              rule.status === "pass" ? "bg-green-900 text-green-300" :
              rule.status === "fail" ? "bg-red-900 text-red-300" :
              "bg-amber-900 text-amber-300"
            }`}>{rule.status}</span>
            {savedNow && <span className="text-xs text-green-400">✓ saved</span>}
          </div>
          <p className="text-xs mt-0.5 opacity-80 line-clamp-2">{rule.message}</p>
        </div>
        <button onClick={() => setExpanded(!expanded)}
          className="text-slate-400 hover:text-white text-xs flex-shrink-0">
          {expanded ? "▲" : "▼"}
        </button>
      </div>

      {expanded && (
        <div className="mt-2 space-y-2">
          {/* Comparison */}
          {(rule.appraisalValue || rule.engagementValue) && (
            <div className="grid grid-cols-2 gap-2 text-xs">
              {rule.appraisalValue && (
                <div className="bg-slate-800/60 rounded p-2">
                  <div className="text-slate-400 text-[10px] uppercase mb-1">Found in Report</div>
                  <div className="font-mono text-slate-200 break-all">{rule.appraisalValue}</div>
                </div>
              )}
              {rule.engagementValue && (
                <div className="bg-blue-900/30 rounded p-2 border border-blue-800/40">
                  <div className="text-blue-400 text-[10px] uppercase mb-1">Expected (Order Form)</div>
                  <div className="font-mono text-blue-200 break-all">{rule.engagementValue}</div>
                </div>
              )}
            </div>
          )}

          {rule.actionItem && (
            <div className="bg-amber-900/20 border border-amber-800/30 rounded p-2 text-xs text-amber-300">
              💡 {rule.actionItem}
            </div>
          )}

          {/* Decision controls — only for review-required items */}
          {rule.reviewRequired && (
            <div className="space-y-1.5">
              <div className="flex gap-2">
                <button
                  onClick={() => onDecision("ACCEPT")}
                  disabled={saving}
                  className={`flex-1 py-1.5 rounded text-xs font-semibold transition-colors ${
                    decision === "ACCEPT"
                      ? "bg-green-600 text-white"
                      : "bg-slate-700 hover:bg-green-900 text-slate-300"
                  }`}
                >
                  {saving && decision === "ACCEPT" ? "…" : "✓ Accept"}
                </button>
                <button
                  onClick={() => onDecision("REJECT")}
                  disabled={saving}
                  className={`flex-1 py-1.5 rounded text-xs font-semibold transition-colors ${
                    decision === "REJECT"
                      ? "bg-red-600 text-white"
                      : "bg-slate-700 hover:bg-red-900 text-slate-300"
                  }`}
                >
                  {saving && decision === "REJECT" ? "…" : "✗ Reject"}
                </button>
              </div>
              <textarea
                value={comment}
                onChange={e => onComment(e.target.value)}
                onBlur={() => decision && onDecision(decision)} // auto-save on blur
                placeholder="Optional comment…"
                rows={2}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

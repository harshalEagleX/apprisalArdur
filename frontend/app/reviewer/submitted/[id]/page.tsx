"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import {
  ArrowLeft, CheckCircle2, XCircle, AlertTriangle, FileText,
  RefreshCw, Send, ClipboardList, BookOpen, ChevronDown,
} from "lucide-react";
import { getQCRules, requestReReview as apiRequestReReview, type QCRuleResult } from "@/lib/api";
import { buildEvidenceModel, cleanRuleValue, evidenceText, parseEvidence } from "@/lib/ruleEvidence";
import { failRejectionLanguage } from "@/lib/ruleLanguage";
import { PageSpinner } from "@/components/shared/Spinner";

type TransactionType = "PURCHASE" | "REFINANCE" | "UNKNOWN";


function detectTransactionType(rules: QCRuleResult[]): TransactionType {
  for (const r of rules) {
    const text = [r.message, evidenceText(r), r.appraisalValue, r.engagementValue]
      .join(" ").toLowerCase();
    if (text.includes("refinance")) return "REFINANCE";
    if (text.includes("purchase")) return "PURCHASE";
  }
  return "UNKNOWN";
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function SubmittedReviewPage() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const qcResultId = Number(id);
  const returnTo = searchParams.get("returnTo") ?? "/reviewer/queue";

  const [rules, setRules]           = useState<QCRuleResult[]>([]);
  const [loading, setLoading]       = useState(true);
  const [requesting, setRequesting] = useState(false);
  const [reReviewDone, setReReviewDone] = useState(false);
  const [reReviewReason, setReReviewReason] = useState("");
  const [showReasonBox, setShowReasonBox] = useState(false);
  const [error, setError]           = useState("");
  const [copied, setCopied]         = useState(false);
  const [questionsOpen, setQuestionsOpen] = useState(false);

  const loadResults = useCallback(() => {
    setLoading(true);
    getQCRules(qcResultId)
      .then(data => setRules(data.map(r => ({
        ...r, status: r.status.toLowerCase(),
        appraisalValue: cleanRuleValue(r.appraisalValue), engagementValue: cleanRuleValue(r.engagementValue),
        extractedValue: cleanRuleValue(r.extractedValue), expectedValue: cleanRuleValue(r.expectedValue),
      }))))
      .catch(() => setError("Could not load review results."))
      .finally(() => setLoading(false));
  }, [qcResultId]);

  useEffect(() => {
    const timer = window.setTimeout(loadResults, 0);
    return () => window.clearTimeout(timer);
  }, [loadResults]);

  const failRules = useMemo(
    () => rules.filter(r => r.status === "fail"),
    [rules]
  );
  const txType = useMemo(() => detectTransactionType(rules), [rules]);
  const rejectionBlocks = useMemo(() =>
    failRules.map(r => ({
      rule: r,
      // Engine rejectionText wins; the shared dev fallback (also used by the
      // active review card) runs only when the engine supplied none, so the
      // same rule reads identically on both screens.
      language: failRejectionLanguage(r).text,
    })),
    [failRules]
  );

  const passCount = rules.filter(r =>
    r.status === "pass" || r.status === "manual_pass"
  ).length;
  const overrideCount = rules.filter(r => r.status === "manual_pass").length;
  const failCount = failRules.length;
  const reviewedRules = rules.filter(r =>
    r.verifyQuestion?.trim()
    || r.reviewerVerified != null
    || r.reviewerComment?.trim()
    || r.reviewRequired
  );

  const fullRejectionText = rejectionBlocks
    .map((b, i) => `${i + 1}. [${b.rule.ruleId}] ${b.language}`)
    .join("\n\n");

  async function requestReReview() {
    if (!reReviewReason.trim()) { setShowReasonBox(true); return; }
    setRequesting(true);
    try {
      await apiRequestReReview(qcResultId, reReviewReason.trim());
      setReReviewDone(true);
    } catch {
      setError("Re-review request failed. Please try again.");
    } finally {
      setRequesting(false);
    }
  }

  async function copyRejectionText() {
    await navigator.clipboard.writeText(fullRejectionText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  }

  if (loading) return <PageSpinner label="Loading review results…" />;

  return (
    <div className="mx-auto max-w-3xl px-5 py-8">
      {/* Header */}
      <div className="mb-6 flex items-start gap-4">
        <a
          href={returnTo}
          className="mt-0.5 flex items-center gap-1.5 text-slate-400 hover:text-white text-sm transition-colors flex-shrink-0"
        >
          <ArrowLeft size={14} /> Queue
        </a>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600">
            Review submitted
          </div>
          <h1 className="mt-1 text-xl font-semibold text-white">
            QC Result #{qcResultId}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded border bg-green-950/50 border-green-500/25 text-green-300">
              <CheckCircle2 size={10} /> {passCount} Pass
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded border bg-red-950/50 border-red-500/25 text-red-300">
              <XCircle size={10} /> {failCount} Fail
            </span>
            {txType !== "UNKNOWN" && (
              <span className="text-[11px] px-2 py-0.5 rounded border border-white/10 bg-[#11161C] text-slate-400">
                {txType}
              </span>
            )}
            {reviewedRules.length > 0 && (
              <a
                href="#review-questions"
                className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded border border-slate-500/30 bg-slate-950/40 text-slate-300 transition-colors hover:bg-white/[0.04] hover:text-white"
              >
                <BookOpen size={10} /> Review questions
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Closure summary — a clear "this review is done" recap, not just a log of questions. */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-white/10 bg-[#11161C] p-3">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Rules reviewed</div>
          <div className="mt-1 text-lg font-semibold tabular-nums text-white">{reviewedRules.length}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-[#11161C] p-3">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Failures confirmed</div>
          <div className="mt-1 text-lg font-semibold tabular-nums text-red-300">{failCount}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-[#11161C] p-3">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Overrides applied</div>
          <div className="mt-1 text-lg font-semibold tabular-nums text-amber-300">{overrideCount}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-[#11161C] p-3">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">Passed</div>
          <div className="mt-1 text-lg font-semibold tabular-nums text-green-300">{passCount}</div>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/25 bg-red-950/40 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {reviewedRules.length > 0 && (
        <div id="review-questions" className="mb-6 space-y-3">
          <button
            type="button"
            onClick={() => setQuestionsOpen(open => !open)}
            aria-expanded={questionsOpen}
            className="flex w-full items-center gap-3 rounded-lg border border-white/10 bg-[#11161C] px-4 py-3 text-left transition-colors hover:bg-white/[0.04]"
          >
            <BookOpen size={14} className="text-slate-400" />
            <span className="flex-1 text-sm font-semibold text-white">
              Saved Review Questions ({reviewedRules.length})
            </span>
            <ChevronDown
              size={15}
              className={`text-slate-500 transition-transform ${questionsOpen ? "rotate-180" : ""}`}
            />
          </button>
          {questionsOpen && (
            <div className="overflow-hidden rounded-lg border border-white/10 bg-[#11161C] divide-y divide-white/10">
              {reviewedRules.map(rule => (
                <ReviewQuestionRow key={rule.id} rule={rule} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Re-review section */}
      <div className="mb-6 rounded-lg border border-white/10 bg-[#11161C] p-4">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-amber-500/25 bg-amber-950/50">
            <RefreshCw size={15} className="text-amber-300" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-white">Request Re-review</div>
            <p className="mt-0.5 text-xs text-slate-400 leading-relaxed">
              If this appraisal needs additional review, send it back to the admin for reassignment.
              An admin notification will be triggered and the file will be reassigned.
            </p>
          </div>
        </div>

        {reReviewDone ? (
          <div className="mt-3 rounded-lg border border-green-500/25 bg-green-950/30 px-3 py-2.5 text-sm text-green-200 flex items-center gap-2">
            <CheckCircle2 size={14} /> Re-review request submitted. Admin has been notified.
          </div>
        ) : (
          <div className="mt-3 space-y-2">
            {showReasonBox && (
              <textarea
                value={reReviewReason}
                onChange={e => setReReviewReason(e.target.value)}
                placeholder="Reason for re-review request (required)..."
                rows={2}
                autoFocus
                className="w-full resize-none rounded-md border border-white/10 bg-[#0B0F14]/70 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 transition-colors focus:border-amber-500/50 focus:outline-none focus:ring-2 focus:ring-amber-500/20"
              />
            )}
            <button
              onClick={requestReReview}
              disabled={requesting}
              className="flex h-9 items-center gap-2 rounded-md border border-amber-500/30 bg-amber-950/40 px-4 text-xs font-semibold text-amber-200 transition-colors hover:bg-amber-900/40 disabled:opacity-50"
            >
              {requesting ? <RefreshCw size={12} className="animate-spin" /> : <Send size={12} />}
              {requesting ? "Sending request…" : showReasonBox ? "Send Re-review Request" : "Request Re-review"}
            </button>
          </div>
        )}
      </div>

      {/* Rejection Language */}
      {rejectionBlocks.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ClipboardList size={14} className="text-slate-400" />
              <span className="text-sm font-semibold text-white">
                Rejection Language ({rejectionBlocks.length} {rejectionBlocks.length === 1 ? "issue" : "issues"})
              </span>
            </div>
            <button
              onClick={copyRejectionText}
              className="flex h-7 items-center gap-1.5 rounded-md border border-white/10 bg-[#11161C] px-3 text-[11px] text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-slate-200"
            >
              {copied ? <><CheckCircle2 size={11} /> Copied!</> : "Copy all"}
            </button>
          </div>

          {txType === "REFINANCE" && rejectionBlocks.some(b => b.rule.ruleId.startsWith("C-")) && (
            <div className="rounded-lg border border-amber-500/25 bg-amber-950/20 px-3 py-2 text-xs text-amber-200 flex items-start gap-2">
              <AlertTriangle size={12} className="flex-shrink-0 mt-0.5" />
              Refinance transaction detected. Contract section (C-rules) must be blank per UAD requirements.
            </div>
          )}

          <div className="space-y-3">
            {rejectionBlocks.map(({ rule, language }) => (
              <RejectionBlock key={rule.id} rule={rule} language={language} />
            ))}
          </div>
        </div>
      )}

      {failRules.length === 0 && (
        <div className="rounded-lg border border-green-500/25 bg-green-950/20 px-5 py-8 text-center">
          <CheckCircle2 size={24} className="mx-auto text-green-400 mb-2" />
          <div className="text-sm font-semibold text-green-200">All rules passed</div>
          <p className="mt-1 text-xs text-slate-400">No rejection language needed for this appraisal.</p>
        </div>
      )}
    </div>
  );
}

// ── Rejection Block ───────────────────────────────────────────────────────────
function RejectionBlock({ rule, language }: { rule: QCRuleResult; language: string }) {
  const [copied, setCopied] = useState(false);
  // The document(s) this rule actually drew values from, from real evidence —
  // not guessed from the rule-id prefix.
  const sourceLabels = Array.from(new Set(parseEvidence(rule).map(s => s.label)));
  const page = rule.pdfPage ? rule.pdfPage : null;

  async function copy() {
    await navigator.clipboard.writeText(language);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="rounded-lg border border-red-500/20 bg-[#11161C] overflow-hidden">
      {/* Rule header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-white/5 bg-red-950/10">
        <span className="font-mono text-[10px] bg-[#0B0F14]/70 border border-white/10 px-1.5 py-0.5 rounded text-slate-400">
          {rule.ruleId}
        </span>
        <span className="text-xs font-medium text-slate-200 flex-1 min-w-0 truncate">
          {rule.ruleName}
        </span>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {sourceLabels.length > 0 && (
            <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border border-slate-500/25 bg-slate-950/40 text-slate-400">
              <BookOpen size={9} /> {sourceLabels.join(" · ")}
            </span>
          )}
          {page && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-white/10 bg-[#0B0F14]/70 text-slate-500 font-mono">
              p.{page}
            </span>
          )}
          <button
            onClick={copy}
            className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border border-white/10 bg-[#0B0F14]/70 text-slate-500 hover:text-slate-300 transition-colors"
          >
            {copied ? <><CheckCircle2 size={9} /> Copied</> : <><FileText size={9} /> Copy</>}
          </button>
        </div>
      </div>

      {/* Evidence — labelled by the document each value actually came from, and
          only shown as a side-by-side comparison when the rule compared two
          documents. Single-document checks render one panel. */}
      {(() => {
        const model = buildEvidenceModel(rule);
        if (model.mode === "none") return null;
        return (
          <div className="border-b border-white/5">
            {model.headline && (
              <div className="px-3 pt-2 text-[10px] text-slate-500">{model.headline}</div>
            )}
            <div
              className={`grid gap-px bg-white/5 ${model.sources.length >= 2 ? "grid-cols-2" : "grid-cols-1"} ${model.headline ? "mt-2" : ""}`}
            >
              {model.sources.map((source, i) => (
                <div key={`${source.document}-${i}`} className="px-3 py-2 bg-[#11161C]">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1">
                    {source.label}
                  </div>
                  <div className="font-mono text-xs text-slate-200 leading-relaxed">
                    {source.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Rejection language */}
      <div className="px-3 py-3">
        {rule.verifyQuestion?.trim() && (
          <div className="mb-3 rounded-md border border-amber-500/20 bg-amber-950/20 px-3 py-2">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-amber-300">
              Review question
            </div>
            <p className="text-xs leading-relaxed text-amber-100/90">{rule.verifyQuestion}</p>
          </div>
        )}
        <div className="text-[10px] font-semibold uppercase tracking-wide text-red-400 mb-1.5">
          Rejection language
        </div>
        <p className="text-xs text-slate-200 leading-relaxed">{language}</p>
      </div>
    </div>
  );
}

function ReviewQuestionRow({ rule }: { rule: QCRuleResult }) {
  const decision = rule.reviewerVerified === true
    ? "PASS"
    : rule.reviewerVerified === false
      ? "FAIL"
      : "Not marked";
  const decisionClass = rule.reviewerVerified === true
    ? "border-green-500/25 bg-green-950/30 text-green-300"
    : rule.reviewerVerified === false
      ? "border-red-500/25 bg-red-950/30 text-red-300"
      : "border-white/10 bg-[#0B0F14]/70 text-slate-400";

  return (
    <div className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-[#0B0F14]/70 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
          {rule.ruleId}
        </span>
        <span className="min-w-0 flex-1 text-xs font-medium text-slate-200">{rule.ruleName}</span>
        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${decisionClass}`}>
          {decision}
        </span>
      </div>
      {rule.verifyQuestion?.trim() && (
        <div className="mt-2 rounded-md border border-amber-500/20 bg-amber-950/15 px-3 py-2">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-amber-300">Generated question</div>
          <p className="text-xs leading-relaxed text-amber-100/90">{rule.verifyQuestion}</p>
        </div>
      )}
      {rule.reviewerComment?.trim() && (
        <div className="mt-2 text-xs leading-relaxed text-slate-400">
          <span className="font-semibold text-slate-300">Reviewer note:</span> {rule.reviewerComment}
        </div>
      )}
    </div>
  );
}


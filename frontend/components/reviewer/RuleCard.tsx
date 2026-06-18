"use client";
import React, { memo, useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Check,
  X,
  AlertTriangle,
  CheckCircle2,
  Save,
} from "lucide-react";
import type { QCRuleResult } from "@/lib/api";
import { EvidenceCompare } from "./EvidenceCompare";
import { buildEvidenceModel } from "@/lib/ruleEvidence";
import { failRejectionLanguage } from "@/lib/ruleLanguage";

type Decision = "PASS" | "FAIL";

const STATUS_STYLE: Record<string, { border: string; bg: string; text: string }> = {
  pass:        { border: "border-green-500/20",  bg: "bg-green-950/10",  text: "text-green-200" },
  fail:        { border: "border-red-500/20",    bg: "bg-red-950/10",    text: "text-red-200" },
  verify:      { border: "border-amber-500/20",  bg: "bg-amber-950/5",  text: "text-amber-200" },
  review:      { border: "border-amber-500/20",  bg: "bg-amber-950/10",  text: "text-amber-200" },
  extraction_failed: { border: "border-amber-500/20", bg: "bg-amber-950/10", text: "text-amber-200" },
  ocr_low_confidence: { border: "border-amber-500/20", bg: "bg-amber-950/10", text: "text-amber-200" },
  source_missing: { border: "border-amber-500/20", bg: "bg-amber-950/10", text: "text-amber-200" },
  system_error: { border: "border-red-500/20", bg: "bg-red-950/10", text: "text-red-200" },
  cross_doc_mismatch: { border: "border-red-500/20", bg: "bg-red-950/10", text: "text-red-200" },
  hold: { border: "border-red-500/30", bg: "bg-red-950/15", text: "text-red-200" },
  skipped: { border: "border-white/8", bg: "bg-white/[0.03]", text: "text-slate-400" },
  not_executed: { border: "border-white/8", bg: "bg-white/[0.03]", text: "text-slate-400" },
  not_applicable: { border: "border-white/8", bg: "bg-white/[0.03]", text: "text-slate-400" },
  MANUAL_PASS: { border: "border-green-500/20",  bg: "bg-green-950/10",  text: "text-green-200" },
};

const SEV_STYLE: Record<string, string> = {
  BLOCKING: "bg-red-950/50 border-red-500/25 text-red-200",
  STANDARD: "bg-[#161B22] border-white/10 text-slate-400",
  ADVISORY: "bg-[#161B22]/70 border-white/10 text-slate-500",
};

function ruleStatus(status: string): string {
  const normalized = status.toLowerCase();
  return normalized === "manual_pass" ? "MANUAL_PASS" : normalized;
}

function isReviewLikeStatus(status: string): boolean {
  return [
    "verify",
    "review",
    "hold",
    "extraction_failed",
    "ocr_low_confidence",
    "source_missing",
    "system_error",
    "cross_doc_mismatch",
  ].includes(status);
}

export interface RuleCardProps {
  rule: QCRuleResult;
  decision?: Decision;
  comment: string;
  saving: boolean;
  savedNow: boolean;
  offline: boolean;
  sessionReady: boolean;
  acknowledged: boolean;
  active?: boolean;
  onSelect: () => void;
  onDecision: (d: Decision) => void;
  onAcknowledge: (checked: boolean) => void;
  onComment: (c: string) => void;
  commentRef: (node: HTMLTextAreaElement | null) => void;
  saveNotice?: { text: string; tone: "success" | "error" | "info" } | null;
  /** Whether a FAIL→Pass override needs a SECOND reviewer (mirrors the backend policy). */
  requireSecondApproval?: boolean;
}

export const RuleCard = memo(function RuleCard({
  rule,
  decision,
  comment,
  saving,
  savedNow,
  offline,
  sessionReady,
  acknowledged,
  active,
  onSelect,
  onDecision,
  onAcknowledge,
  onComment,
  commentRef,
  requireSecondApproval = true,
}: RuleCardProps) {
  const normalizedStatus = ruleStatus(rule.status);
  const [expanded, setExpanded] = useState(
    normalizedStatus === "fail" || isReviewLikeStatus(normalizedStatus)
  );
  const [now, setNow] = useState(0);

  const s = STATUS_STYLE[normalizedStatus] ?? STATUS_STYLE["verify"];
  const sev = rule.severity ?? "STANDARD";
  const isVerify = isReviewLikeStatus(normalizedStatus);
  const isFail = normalizedStatus === "fail";
  const evidenceModel = buildEvidenceModel(rule);
  // EvidenceCompare carries the full finding text (its "why" box). Show evidence
  // whenever there's something to explain so we don't repeat the same sentence.
  const showEvidence = evidenceModel.mode !== "none" || isFail || isVerify;
  // The Python engine echoes `message` into `action_item` for review rules, so the
  // action-item box is almost always a duplicate of the finding. Only show it when
  // it is a genuinely distinct instruction.
  const actionItemText = (rule.actionItem ?? "").trim();
  const showActionItem =
    actionItemText.length > 0 &&
    actionItemText.toLowerCase() !== "no reviewer action required." &&
    actionItemText !== (rule.message ?? "").trim() &&
    actionItemText !== (rule.verifyQuestion ?? "").trim() &&
    actionItemText !== (rule.rejectionText ?? "").trim();
  const isBlockingVerify = isVerify && sev === "BLOCKING";

  const presentedAt = rule.firstPresentedAt ? new Date(rule.firstPresentedAt).getTime() : 0;
  const elapsedMs = presentedAt > 0 && now > 0 ? Math.max(0, now - presentedAt) : 0;
  const waitMs = isVerify && presentedAt > 0 ? Math.max(0, 8000 - elapsedMs) : 0;
  const waitSeconds = Math.ceil(waitMs / 1000);

  const slaMs = rule.reviewRequired ? 4 * 60 * 60 * 1000 - elapsedMs : null;
  const slaExpired = slaMs != null && slaMs <= 0;
  const slaUnderHour = slaMs != null && slaMs > 0 && slaMs <= 60 * 60 * 1000;
  const slaLabel =
    slaMs == null
      ? null
      : slaExpired
        ? "Needs supervisor attention"
        : `${Math.floor(slaMs / 3_600_000)}h ${Math.floor((slaMs % 3_600_000) / 60_000)}m remaining`;

  const overrideReasonOk = !isFail || comment.trim().length >= 20;
  const canAct =
    sessionReady && !offline && !saving && waitMs === 0 && (!isBlockingVerify || acknowledged);
  const canPass = canAct && overrideReasonOk;
  const canFail = canAct && (isVerify || isFail);

  // SLA / wait countdown timer — only mount when needed
  useEffect(() => {
    if (!rule.reviewRequired && !isVerify) return;
    const tick = () => setNow(Date.now());
    const startTimer = window.setTimeout(tick, 0);
    const interval = window.setInterval(tick, 500);
    return () => {
      window.clearTimeout(startTimer);
      window.clearInterval(interval);
    };
  }, [isVerify, rule.reviewRequired]);

  const spinnerSvg = (
    <svg
      className="animate-spin h-3 w-3"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );

  return (
    <div
      id={`rule-${rule.id}`}
      className={`rounded-lg border p-3 backdrop-blur-md backdrop-saturate-150 shadow-[0_10px_24px_rgba(0,0,0,0.12)] ${s.border} ${s.bg} ${active ? "ring-1 ring-slate-500/50" : ""}`}
    >
      <button
        onClick={() => {
          setExpanded(!expanded);
          onSelect();
        }}
        className="w-full text-left"
      >
        <div className="flex items-start gap-2">
          <span className="font-mono text-[10px] bg-[#0B0F14]/70 border border-white/10 px-1.5 py-0.5 rounded text-slate-400 flex-shrink-0 mt-0.5">
            {rule.ruleId}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs font-medium text-slate-200">{rule.ruleName}</span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${SEV_STYLE[sev] ?? SEV_STYLE.STANDARD}`}
              >
                {sev}
              </span>
              {saving && (
                <span className="text-[10px] text-slate-300 flex items-center gap-0.5">
                  <Save size={9} />
                  saving
                </span>
              )}
              {!saving && savedNow && (
                <span className="text-[10px] text-green-300 flex items-center gap-0.5">
                  <CheckCircle2 size={9} />
                  saved
                </span>
              )}
              {!saving && decision && !savedNow && (
                <span className="text-[10px] text-green-300 flex items-center gap-0.5">
                  <CheckCircle2 size={9} />
                  saved earlier
                </span>
              )}
              {rule.overridePending && (
                <span className="text-[10px] text-slate-200 border border-slate-500/25 bg-slate-950/35 rounded px-1.5 py-0.5">
                  second approval pending
                </span>
              )}
              {slaLabel && (
                <span
                  className={`text-[10px] rounded border px-1.5 py-0.5 ${
                    slaExpired
                      ? "border-red-500/35 bg-red-950/45 text-red-200"
                      : slaUnderHour
                        ? "border-amber-500/30 bg-amber-950/35 text-amber-200"
                        : "border-white/10 bg-[#0B0F14]/60 text-slate-400"
                  }`}
                >
                  {slaLabel}
                </span>
              )}
            </div>
            {!(expanded && showEvidence) && (
              <p className={`text-xs mt-0.5 leading-relaxed ${s.text} opacity-80 line-clamp-2`}>
                {isVerify && rule.verifyQuestion
                  ? rule.verifyQuestion
                  : isFail
                    ? failRejectionLanguage(rule).text
                    : rule.message}
              </p>
            )}
          </div>
          <div className="flex-shrink-0 text-slate-600">
            {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="mt-3 space-y-2.5">
          {showEvidence && <EvidenceCompare rule={rule} status={normalizedStatus} />}

          {showActionItem && (
            <div className="flex items-start gap-2 bg-amber-950/18 border border-amber-500/25 rounded-lg p-2.5 text-xs text-amber-200">
              <AlertTriangle size={11} className="flex-shrink-0 mt-0.5" />
              <span className="leading-relaxed">{actionItemText}</span>
            </div>
          )}

          {rule.confidence != null && (() => {
            // Frame confidence qualitatively so a bare "100%" doesn't invite blind trust.
            // Low confidence is flagged amber (verify carefully); the raw % is secondary.
            const c = Number(rule.confidence);
            const band = c >= 0.85
              ? { label: "High confidence", cls: "text-slate-300" }
              : c >= 0.6
                ? { label: "Moderate confidence", cls: "text-slate-300" }
                : { label: "Low confidence — verify carefully", cls: "text-amber-300" };
            return (
              <div className={`flex items-center gap-1.5 text-[11px] ${band.cls}`}>
                <span className="font-medium">{band.label}</span>
                <span className="font-mono text-slate-500">· {Math.round(c * 100)}%</span>
              </div>
            );
          })()}

          {isVerify && (
            <details className="rounded-lg border border-white/10 bg-[#0B0F14]/55 px-2.5 py-2 text-xs text-slate-400">
              <summary className="cursor-pointer text-slate-300 font-medium">Rule help</summary>
              <div className="mt-2 space-y-2 leading-relaxed">
                <p>
                  {rule.help?.summary ??
                    "Review the referenced values and document location before choosing Pass or Fail."}
                </p>
                {rule.help?.example && <p className="text-slate-500">{rule.help.example}</p>}
                {rule.help?.terms && Object.keys(rule.help.terms).length > 0 && (
                  <div className="grid gap-1">
                    {Object.entries(rule.help.terms).map(([term, meaning]) => (
                      <div key={term} className="flex gap-2">
                        <span className="font-mono text-slate-300 min-w-16">{term}</span>
                        <span>{meaning}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </details>
          )}

          {rule.reviewRequired ? (
            <div className="space-y-2">
              {isVerify && waitMs > 0 && (
                <div className="text-[11px] text-amber-200 bg-amber-950/18 border border-amber-500/25 rounded-lg px-2.5 py-2">
                  Read the question and document reference. Actions unlock in {waitSeconds}s.
                </div>
              )}
              {isBlockingVerify && (
                <label className="flex items-start gap-2 text-[11px] text-slate-300 bg-[#0B0F14]/55 border border-white/10 rounded-lg px-2.5 py-2">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={e => onAcknowledge(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>I have reviewed the referenced document sections.</span>
                </label>
              )}
              {isFail && (
                <div className="text-[11px] text-red-200 bg-red-950/18 border border-red-500/25 rounded-lg px-2.5 py-2">
                  <strong>Confirm issue</strong> to acknowledge this finding — it stays as an issue in the final report.
                  To override to no-issue, enter a specific reason (at least 20 characters)
                  {requireSecondApproval ? "; a second reviewer must approve the override before sign-off." : "."}
                </div>
              )}
              {rule.overridePending && (
                <div className="text-[11px] text-slate-200 bg-slate-950/18 border border-slate-500/25 rounded-lg px-2.5 py-2">
                  {requireSecondApproval ? (
                    <>Override requested by {rule.overrideRequestedBy ?? "another reviewer"}. A
                    different reviewer must approve the no-issue override.</>
                  ) : (
                    <>Override requested by {rule.overrideRequestedBy ?? "a reviewer"}. Press
                    Override — no issue to approve it (single-reviewer mode).</>
                  )}
                </div>
              )}

              {/* Fail rules: Confirm Fail is the PRIMARY (safe, expected) action — wider + emphasized.
                  Override to Pass is the high-risk exception: narrower, muted, gated on a reason. */}
              {isFail && (
                <div className="flex gap-2">
                  <button
                    onClick={() => onDecision("FAIL")}
                    disabled={!canFail}
                    className={`flex-[1.5] flex items-center justify-center gap-1.5 h-8 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 ${
                      decision === "FAIL"
                        ? "bg-red-600 text-white"
                        : "bg-red-950/30 border border-red-500/30 text-red-200 hover:bg-red-950/50"
                    }`}
                  >
                    {saving ? spinnerSvg : <X size={12} />} Confirm issue
                  </button>
                  <button
                    onClick={() => onDecision("PASS")}
                    disabled={!canPass}
                    title={!overrideReasonOk ? "Add a specific override reason (min 20 chars) to enable" : "High-risk: override this finding to No-issue"}
                    className={`flex-1 flex items-center justify-center gap-1.5 h-8 rounded-lg text-[11px] font-medium transition-colors disabled:opacity-40 ${
                      decision === "PASS"
                        ? "bg-green-600 text-white font-semibold"
                        : "bg-transparent hover:bg-green-950/30 hover:text-green-200 text-slate-500 border border-white/10"
                    }`}
                  >
                    {saving ? spinnerSvg : <Check size={12} />} Override — no issue
                  </button>
                </div>
              )}

              {/* Verify rules: Save Pass (primary) + Save Fail (secondary) */}
              {isVerify && (
                <div className="flex gap-2">
                  <button
                    onClick={() => onDecision("PASS")}
                    disabled={!canPass}
                    className={`flex-1 flex items-center justify-center gap-1.5 h-8 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 ${
                      decision === "PASS"
                        ? "bg-green-600 text-white"
                        : "bg-[#161B22] hover:bg-green-950/35 hover:text-green-200 text-slate-400 border border-white/10"
                    }`}
                  >
                    {saving ? spinnerSvg : <Check size={12} />} No issue
                  </button>
                  <button
                    onClick={() => onDecision("FAIL")}
                    disabled={!canFail}
                    className={`flex-1 flex items-center justify-center gap-1.5 h-8 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 ${
                      decision === "FAIL"
                        ? "bg-red-600 text-white"
                        : "bg-[#161B22] hover:bg-red-950/35 hover:text-red-200 text-slate-400 border border-white/10"
                    }`}
                  >
                    {saving ? spinnerSvg : <X size={12} />} Issue found
                  </button>
                </div>
              )}

              <textarea
                ref={commentRef}
                value={comment}
                onChange={e => onComment(e.target.value)}
                placeholder={
                  isFail
                    ? "Reason for no-issue override — be specific (minimum 20 characters). Leave blank to confirm issue."
                    : "Add a comment (optional)..."
                }
                rows={2}
                className="w-full resize-none rounded-md border border-white/10 bg-[#0B0F14]/55 px-2.5 py-2 text-xs text-slate-300 placeholder-slate-600 transition-colors focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30"
              />
              {decision && (
                <div className="text-[10px] text-slate-600">
                  {isFail ? "Decision stored — Confirm issue or Override — no issue." : "Comments are stored when you press No issue or Issue found."}
                </div>
              )}
            </div>
          ) : (
            <div className={`flex items-center gap-1.5 text-xs ${s.text} opacity-60`}>
              {normalizedStatus === "pass" || normalizedStatus === "MANUAL_PASS" ? (
                <>
                  <CheckCircle2 size={11} /> No action required
                </>
              ) : null}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

export default RuleCard;

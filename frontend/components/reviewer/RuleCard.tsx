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

type Decision = "PASS" | "FAIL";

const STATUS_STYLE: Record<string, { border: string; bg: string; text: string }> = {
  pass:        { border: "border-green-800/40",  bg: "bg-green-950/20",  text: "text-green-300" },
  fail:        { border: "border-red-800/40",    bg: "bg-red-950/20",    text: "text-red-300" },
  verify:      { border: "border-amber-800/40",  bg: "bg-amber-950/20",  text: "text-amber-300" },
  MANUAL_PASS: { border: "border-teal-800/40",   bg: "bg-teal-950/20",   text: "text-teal-300" },
};

const SEV_STYLE: Record<string, string> = {
  BLOCKING: "bg-red-950/60 border-red-800/50 text-red-400",
  STANDARD: "bg-slate-800 border-slate-700 text-slate-400",
  ADVISORY: "bg-slate-800/50 border-slate-700/50 text-slate-500",
};

function ruleStatus(status: string): string {
  const normalized = status.toLowerCase();
  return normalized === "manual_pass" ? "MANUAL_PASS" : normalized;
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
}: RuleCardProps) {
  const normalizedStatus = ruleStatus(rule.status);
  const [expanded, setExpanded] = useState(
    normalizedStatus === "fail" || normalizedStatus === "verify"
  );
  const [now, setNow] = useState(0);

  const s = STATUS_STYLE[normalizedStatus] ?? STATUS_STYLE["verify"];
  const sev = rule.severity ?? "STANDARD";
  const isVerify = normalizedStatus === "verify";
  const isFail = normalizedStatus === "fail";
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
  const canFail = canAct && isVerify;

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
      className={`rounded-xl border p-3 ${s.border} ${s.bg} ${active ? "ring-1 ring-amber-400/70" : ""}`}
    >
      <button
        onClick={() => {
          setExpanded(!expanded);
          onSelect();
        }}
        className="w-full text-left"
      >
        <div className="flex items-start gap-2">
          <span className="font-mono text-[10px] bg-slate-800/60 border border-slate-700/40 px-1.5 py-0.5 rounded text-slate-400 flex-shrink-0 mt-0.5">
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
                <span className="text-[10px] text-blue-300 flex items-center gap-0.5">
                  <Save size={9} />
                  saving
                </span>
              )}
              {!saving && savedNow && (
                <span className="text-[10px] text-teal-400 flex items-center gap-0.5">
                  <CheckCircle2 size={9} />
                  saved
                </span>
              )}
              {!saving && decision && !savedNow && (
                <span className="text-[10px] text-teal-400 flex items-center gap-0.5">
                  <CheckCircle2 size={9} />
                  saved earlier
                </span>
              )}
              {rule.overridePending && (
                <span className="text-[10px] text-blue-300 border border-blue-800/50 bg-blue-950/40 rounded px-1.5 py-0.5">
                  second approval pending
                </span>
              )}
              {slaLabel && (
                <span
                  className={`text-[10px] rounded border px-1.5 py-0.5 ${
                    slaExpired
                      ? "border-red-700/60 bg-red-950/50 text-red-200"
                      : slaUnderHour
                        ? "border-amber-700/50 bg-amber-950/40 text-amber-200"
                        : "border-slate-700/50 bg-slate-900/60 text-slate-400"
                  }`}
                >
                  {slaLabel}
                </span>
              )}
            </div>
            <p className={`text-xs mt-0.5 leading-relaxed ${s.text} opacity-80 line-clamp-2`}>
              {normalizedStatus === "verify" && rule.verifyQuestion
                ? rule.verifyQuestion
                : normalizedStatus === "fail" && rule.rejectionText
                  ? rule.rejectionText
                  : rule.message}
            </p>
          </div>
          <div className="flex-shrink-0 text-slate-600">
            {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="mt-3 space-y-2.5">
          {(rule.appraisalValue ||
            rule.engagementValue ||
            rule.extractedValue ||
            rule.expectedValue) && <EvidenceCompare rule={rule} status={normalizedStatus} />}

          {rule.actionItem && (
            <div className="flex items-start gap-2 bg-amber-950/20 border border-amber-800/20 rounded-lg p-2.5 text-xs text-amber-300">
              <AlertTriangle size={11} className="flex-shrink-0 mt-0.5" />
              <span className="leading-relaxed">{rule.actionItem}</span>
            </div>
          )}

          {rule.confidence != null && (
            <div className="text-[11px] text-slate-500 font-mono">
              Confidence {Math.round(Number(rule.confidence) * 100)}%
            </div>
          )}

          {isVerify && (
            <details className="rounded-lg border border-slate-800 bg-slate-900/60 px-2.5 py-2 text-xs text-slate-400">
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
                <div className="text-[11px] text-amber-300 bg-amber-950/20 border border-amber-800/30 rounded-lg px-2.5 py-2">
                  Read the question and document reference. Actions unlock in {waitSeconds}s.
                </div>
              )}
              {isBlockingVerify && (
                <label className="flex items-start gap-2 text-[11px] text-slate-300 bg-slate-900/70 border border-slate-800 rounded-lg px-2.5 py-2">
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
                <div className="text-[11px] text-red-200 bg-red-950/20 border border-red-800/30 rounded-lg px-2.5 py-2">
                  PASS here is an override. Enter a specific reason of at least 20 characters; a
                  second reviewer must approve it before sign-off.
                </div>
              )}
              {rule.overridePending && (
                <div className="text-[11px] text-blue-200 bg-blue-950/20 border border-blue-800/30 rounded-lg px-2.5 py-2">
                  Override requested by {rule.overrideRequestedBy ?? "another reviewer"}. A
                  different reviewer must press Pass to approve it.
                </div>
              )}
              <div className="flex gap-2">
                <button
                  onClick={() => onDecision("PASS")}
                  disabled={!canPass}
                  className={`flex-1 flex items-center justify-center gap-1.5 h-8 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 ${
                    decision === "PASS"
                      ? "bg-green-600 text-white"
                      : "bg-slate-800 hover:bg-green-900/40 hover:text-green-300 text-slate-400 border border-slate-700"
                  }`}
                >
                  {saving ? spinnerSvg : <Check size={12} />} Save Pass
                </button>
                {normalizedStatus === "verify" && (
                  <button
                    onClick={() => onDecision("FAIL")}
                    disabled={!canFail}
                    className={`flex-1 flex items-center justify-center gap-1.5 h-8 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 ${
                      decision === "FAIL"
                        ? "bg-red-600 text-white"
                        : "bg-slate-800 hover:bg-red-900/40 hover:text-red-300 text-slate-400 border border-slate-700"
                    }`}
                  >
                    {saving ? spinnerSvg : <X size={12} />} Save Fail
                  </button>
                )}
              </div>
              <textarea
                ref={commentRef}
                value={comment}
                onChange={e => onComment(e.target.value)}
                placeholder={
                  isFail
                    ? "Reason for override - be specific (minimum 20 characters)."
                    : "Add a comment (optional)..."
                }
                rows={2}
                className="w-full bg-slate-800/50 border border-slate-700/40 rounded-lg px-2.5 py-2 text-xs text-slate-300 placeholder-slate-600 resize-none focus:outline-none focus:ring-1 focus:ring-blue-600/50 transition-colors"
              />
              {decision && (
                <div className="text-[10px] text-slate-600">
                  Comments are stored when you press Save Pass or Save Fail.
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

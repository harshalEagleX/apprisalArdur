"use client";
import React, { memo, useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Check,
  X,
  Save,
  CheckCircle2,
  Camera,
} from "lucide-react";
import type { QCRuleResult, RuleDetail } from "@/lib/api";
import { getRuleDetail } from "@/lib/api";
import { documentLabel } from "@/lib/ruleEvidence";
import { failRejectionLanguage } from "@/lib/ruleLanguage";
import { ruleStatus, isReviewLikeStatus } from "@/lib/ruleStatus";

type Decision = "PASS" | "FAIL";

/**
 * The production reviewer finding row. Collapsed-by-default and slim (~48px):
 * severity dot, the backend-owned one-liner summary, a plain-language confidence
 * chip, and a chevron — no document names, match-%, or reasoning paragraphs until
 * expanded. On expand it lazy-loads the full evidence (`/detail`) and renders clean
 * label+value source cards (no raw-snippet token noise), the explanation, and the
 * status-appropriate decision controls. Drop-in replacement for RuleCard: it takes
 * the same control props so the verify page wiring is unchanged.
 */
export interface FindingRowProps {
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
}

// Severity intent drives the dot, its glow ring, the card tint, and the confidence
// chip hue (the chip colour follows severity, never confidence — per the design).
const SEV = {
  issue: {
    dot: "bg-red-400",
    glow: "shadow-[0_0_0_3px_rgba(239,68,68,0.16)]",
    card: "border-red-500/20 bg-red-950/[0.06]",
    chip: "border-red-500/25 bg-red-950/30 text-red-300",
  },
  check: {
    dot: "bg-amber-400",
    glow: "shadow-[0_0_0_3px_rgba(245,158,11,0.16)]",
    card: "border-amber-500/20 bg-amber-950/[0.05]",
    chip: "border-amber-500/25 bg-amber-950/30 text-amber-300",
  },
  pass: {
    dot: "bg-green-400",
    glow: "shadow-[0_0_0_3px_rgba(34,197,94,0.16)]",
    card: "border-green-500/20 bg-green-950/[0.06]",
    chip: "border-green-500/25 bg-green-950/30 text-green-300",
  },
} as const;

type Sev = keyof typeof SEV;

function severityFor(status: string): Sev {
  if (status === "fail" || status === "hold" || status === "cross_doc_mismatch" || status === "system_error") {
    return "issue";
  }
  if (status === "pass" || status === "MANUAL_PASS" || status === "not_applicable") {
    return "pass";
  }
  return "check";
}

// Backend tier (high|medium|low) → a 1-2 word reviewer label. Falls back to the raw
// confidence score only when the backend tier is absent (legacy rows).
function tierLabel(tier: string | null | undefined, confidence: number | null | undefined): string {
  const t = (tier || "").toLowerCase();
  if (t === "high") return "High confidence";
  if (t === "medium") return "Double-check";
  if (t === "low") return "Verify manually";
  const pct = Math.round((confidence ?? 0) * 100);
  if (pct >= 75) return "High confidence";
  if (pct >= 41) return "Double-check";
  return "Verify manually";
}

/** Emphasize the cited values (from `highlightedValues`) inside the summary line. */
function renderSummary(summary: string, highlights?: string[] | null): React.ReactNode {
  if (!highlights || highlights.length === 0) return summary;
  const escaped = highlights
    .filter(Boolean)
    .map(v => v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (escaped.length === 0) return summary;
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  return summary.split(pattern).map((part, i) =>
    highlights.some(v => v.toLowerCase() === part.toLowerCase()) ? (
      <span key={i} className="font-semibold text-gold">{part}</span>
    ) : (
      <React.Fragment key={i}>{part}</React.Fragment>
    )
  );
}

export const FindingRow = memo(function FindingRow({
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
}: FindingRowProps) {
  const status = ruleStatus(rule.status);
  const isVerify = isReviewLikeStatus(status);
  const isFail = status === "fail";
  const sev = severityFor(status);
  const s = SEV[sev];

  const [expanded, setExpanded] = useState(isFail || isVerify);
  const [detail, setDetail] = useState<RuleDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [now, setNow] = useState(0);

  const sevTag = rule.severity ?? "STANDARD";
  const isBlockingVerify = isVerify && sevTag === "BLOCKING";

  // SHALqc queue-noise grouping: a card the system could not auto-judge
  // (needs_data) or could not bind to a field (unauthored) still needs a human,
  // but is NOT a property finding — a small chip tells the reviewer that apart.
  const groupTag =
    rule.cardGroup === "needs_data"
      ? { label: "Couldn't auto-judge", cls: "border-amber-500/30 bg-amber-950/40 text-amber-200" }
      : rule.cardGroup === "unauthored"
        ? { label: "Weakly bound", cls: "border-slate-500/30 bg-slate-800/50 text-slate-300" }
        : null;

  // The collapsed one-liner: the backend-owned summary, falling back to the
  // status-appropriate text for legacy rows that predate the slim contract.
  const summaryText =
    (rule.summary && rule.summary.trim())
      ? rule.summary
      : isVerify && rule.verifyQuestion
        ? rule.verifyQuestion
        : isFail
          ? failRejectionLanguage(rule).text
          : rule.message;

  // Lazy-load the verbose evidence only once, the first time the row expands.
  useEffect(() => {
    if (!expanded || detail || detailLoading) return;
    setDetailLoading(true);
    getRuleDetail(rule.id)
      .then(setDetail)
      .catch(() => undefined)
      .finally(() => setDetailLoading(false));
  }, [expanded, detail, detailLoading, rule.id]);

  // SLA / wait countdown — only mounts for rules that need a reviewer.
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

  const canAct =
    sessionReady && !offline && !saving && waitMs === 0 && (!isBlockingVerify || acknowledged);
  const canPass = canAct;
  const canFail = canAct && (isVerify || isFail);

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
    <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );

  const sources = detail?.sources ?? [];
  const explanation = (detail?.explanation && detail.explanation.trim())
    ? detail.explanation
    : isVerify && rule.verifyQuestion
      ? rule.verifyQuestion
      : isFail
        ? failRejectionLanguage(rule).text
        : rule.message;

  return (
    <div
      id={`rule-${rule.id}`}
      className={`rounded-[10px] border ${s.card} ${active ? "ring-1 ring-slate-500/50" : ""}`}
    >
      {/* ── Collapsed slim row (~48px): dot · summary · tier chip · chevron ── */}
      <button
        onClick={() => {
          setExpanded(v => !v);
          onSelect();
        }}
        aria-expanded={expanded}
        className="flex min-h-[48px] w-full items-center gap-2.5 px-3 py-2 text-left outline-none focus-visible:ring-1 focus-visible:ring-gold/40 rounded-[10px]"
      >
        <span className={`h-2 w-2 flex-shrink-0 rounded-full ${s.dot} ${s.glow}`} aria-hidden />

        <span className="flex-1 min-w-0 truncate text-[14.5px] leading-snug text-slate-100">
          {renderSummary(summaryText, rule.highlightedValues)}
        </span>

        {saving && (
          <span className="hidden sm:flex flex-shrink-0 items-center gap-0.5 text-[10px] text-slate-300">
            <Save size={9} /> saving
          </span>
        )}
        {!saving && (savedNow || (decision != null)) && (
          <span className="hidden sm:flex flex-shrink-0 items-center gap-0.5 text-[10px] text-green-300">
            <CheckCircle2 size={9} /> {savedNow ? "saved" : "saved earlier"}
          </span>
        )}

        {groupTag && (
          <span
            className={`hidden md:inline-flex flex-shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${groupTag.cls}`}
            title="This item still needs a human, but it is a system limitation, not a property finding."
          >
            {groupTag.label}
          </span>
        )}

        {/* The verdict beside this is real and stands on its own; the check ALSO
            depends on photos the engine cannot see. Icon-only here to keep the
            48px row uncluttered — the expanded panel spells it out. */}
        {rule.photoVerificationRequired && (
          <span
            className="hidden sm:inline-flex flex-shrink-0 items-center gap-1 rounded-full border border-sky-500/30 bg-sky-950/40 px-2 py-0.5 text-[11px] font-medium text-sky-200"
            title="Check the photos/sketch by eye — the automated verdict covers only the text part of this check."
          >
            <Camera size={10} aria-hidden /> Photo
          </span>
        )}

        <span
          className={`hidden sm:inline-flex flex-shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${s.chip}`}
        >
          {tierLabel(rule.confidenceTier, rule.confidence)}
        </span>

        <span className="flex-shrink-0 text-slate-600" aria-hidden>
          {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </span>
      </button>

      {/* ── Expanded: clean label+value cards · explanation · controls ── */}
      {expanded && (
        <div className="space-y-2.5 border-t border-white/[0.06] px-3 pb-3 pt-3">
          {/* Rule name + internal code (muted, for support traceability) */}
          <div className="flex items-center gap-1.5 flex-wrap text-slate-400">
            <span className="text-[11px] font-medium text-slate-300">{rule.ruleName}</span>
            <span className="font-mono text-[9px] text-slate-500/70" title="Internal rule code (for support)">
              {rule.ruleId}
            </span>
            {slaLabel && (
              <span
                className={`text-[10px] rounded border px-1.5 py-0.5 ${
                  slaExpired
                    ? "border-red-500/35 bg-red-950/45 text-red-200"
                    : slaUnderHour
                      ? "border-amber-500/30 bg-amber-950/35 text-amber-200"
                      : "border-white/10 bg-sunken/60 text-slate-400"
                }`}
              >
                {slaLabel}
              </span>
            )}
          </div>

          {/* Clean source cards: document label + value only (no %, no token noise). */}
          {detailLoading && sources.length === 0 && (
            <div className="text-[11px] text-slate-600">Loading evidence…</div>
          )}
          {sources.length > 0 && (
            <div className={`grid gap-2 ${sources.length === 1 ? "grid-cols-1" : "grid-cols-2"}`}>
              {sources.map((src, i) => (
                <div key={i} className="rounded-lg border border-white/10 bg-surface/80 p-2.5">
                  <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-slate-500">
                    {src.comparable ? `${src.comparable} · ` : ""}
                    {documentLabel(src.document ?? "")}
                  </div>
                  <div className="text-xs leading-relaxed text-slate-200">{src.value}</div>
                </div>
              ))}
            </div>
          )}

          {/* Plain-language explanation — one short paragraph, no "Reasoning:" prefix. */}
          {explanation && explanation.trim() && (
            <p className="text-xs leading-relaxed text-slate-400">{explanation}</p>
          )}

          {/* Spelled out on expand: the reviewer is about to accept or reject, and
              must know the verdict above covers only what the engine could READ. */}
          {rule.photoVerificationRequired && (
            <div className="flex items-start gap-2 rounded-lg border border-sky-500/25 bg-sky-950/25 px-2.5 py-2">
              <Camera size={13} className="mt-0.5 flex-shrink-0 text-sky-300" aria-hidden />
              <p className="text-xs leading-relaxed text-sky-100">
                This check also depends on photos or the sketch, which the automated
                review cannot see. The result above covers the written values only —
                please confirm the images before you decide.
              </p>
            </div>
          )}

          {/* Decision controls — ported from RuleCard so the review flow is unchanged. */}
          {rule.reviewRequired ? (
            <div className="space-y-2">
              {isVerify && waitMs > 0 && (
                <div className="text-[11px] text-amber-200 bg-amber-950/18 border border-amber-500/25 rounded-lg px-2.5 py-2">
                  Read the question and document reference. Actions unlock in {waitSeconds}s.
                </div>
              )}
              {isBlockingVerify && (
                <label className="flex items-start gap-2 text-[11px] text-slate-300 bg-sunken/55 border border-white/10 rounded-lg px-2.5 py-2">
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
                  Press <strong>Confirm issue</strong> to keep this in the report, or
                  <strong> No issue</strong> to pass it. A comment is optional but recommended.
                </div>
              )}

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
                    title="Pass this finding (No issue)"
                    className={`flex-1 flex items-center justify-center gap-1.5 h-8 rounded-lg text-[11px] font-medium transition-colors disabled:opacity-40 ${
                      decision === "PASS"
                        ? "bg-green-600 text-white font-semibold"
                        : "bg-transparent hover:bg-green-950/30 hover:text-green-200 text-slate-500 border border-white/10"
                    }`}
                  >
                    {saving ? spinnerSvg : <Check size={12} />} No issue
                  </button>
                </div>
              )}

              {isVerify && (
                <div className="flex gap-2">
                  <button
                    onClick={() => onDecision("PASS")}
                    disabled={!canPass}
                    className={`flex-1 flex items-center justify-center gap-1.5 h-8 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 ${
                      decision === "PASS"
                        ? "bg-green-600 text-white"
                        : "bg-muted hover:bg-green-950/35 hover:text-green-200 text-slate-400 border border-white/10"
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
                        : "bg-muted hover:bg-red-950/35 hover:text-red-200 text-slate-400 border border-white/10"
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
                    ? "Why is this fine? (optional) Leave blank to keep the issue."
                    : "Add a comment (optional)…"
                }
                rows={2}
                className="w-full resize-none rounded-md border border-white/10 bg-sunken/55 px-2.5 py-2 text-xs text-slate-300 placeholder-slate-600 transition-colors focus:border-gold/40 focus:outline-none focus:ring-1 focus:ring-gold/25"
              />
              {decision && (
                <div className="text-[10px] text-slate-600">
                  {isFail ? "Decision stored — Confirm issue or No issue." : "Comments are stored when you press No issue or Issue found."}
                </div>
              )}
            </div>
          ) : (
            (status === "pass" || status === "MANUAL_PASS") && (
              <div className="flex items-center gap-1.5 text-xs text-green-300/70">
                <CheckCircle2 size={11} /> No action required
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
});

export default FindingRow;

"use client";
import React from "react";
import type { QCRuleResult } from "@/lib/api";
import { buildEvidenceModel, type EvidenceSource } from "@/lib/ruleEvidence";
import { failRejectionLanguage } from "@/lib/ruleLanguage";

function tokenize(value: string): string[] {
  return value.split(/(\s+|[,;:()[\]{}]+)/).filter(token => token.length > 0);
}

function normalizeToken(value: string): string {
  return value.trim().toLowerCase().replace(/^[^\w.%-]+|[^\w.%-]+$/g, "");
}

/**
 * One document's value. `compareTo` is the set of normalized tokens found in the
 * *other* documents being compared — tokens absent there are highlighted so the
 * reviewer's eye lands on the difference. In single-document mode `compareTo` is
 * empty, so nothing is highlighted (there is nothing to differ from).
 */
function EvidencePanel({
  source,
  compareTo,
  showMeta,
}: {
  source: EvidenceSource;
  compareTo: Set<string>;
  showMeta: boolean;
}) {
  const conf = source.confidence != null ? Math.round(source.confidence * 100) : null;
  return (
    <div className="rounded-lg border border-white/10 bg-[#11161C]/80 p-2.5">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="flex items-baseline gap-1.5 min-w-0">
          {source.comparable && (
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-200 flex-shrink-0">
              {source.comparable}
            </span>
          )}
          <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500 truncate">
            {source.label}
          </span>
        </span>
        {showMeta && (
          <span className="text-[10px] font-mono text-slate-600">
            {source.page ? `p${source.page}` : ""}
            {source.page && conf != null ? " · " : ""}
            {conf != null ? `${conf}%` : ""}
          </span>
        )}
      </div>
      <div className="font-mono text-xs leading-relaxed text-slate-200">
        {tokenize(source.value).map((token, index) => {
          const normalized = normalizeToken(token);
          const mismatch =
            compareTo.size > 0 && Boolean(normalized) && !compareTo.has(normalized);
          return (
            <span
              key={`${token}-${index}`}
              className={
                mismatch
                  ? "rounded bg-amber-400/18 px-0.5 text-amber-200 ring-1 ring-amber-400/20"
                  : undefined
              }
            >
              {token}
            </span>
          );
        })}
      </div>
    </div>
  );
}

export interface EvidenceCompareProps {
  rule: QCRuleResult;
  status: string;
}

export function EvidenceCompare({ rule, status }: EvidenceCompareProps) {
  const model = buildEvidenceModel(rule);

  const reviewLike = [
    "verify",
    "review",
    "hold",
    "extraction_failed",
    "ocr_low_confidence",
    "source_missing",
    "system_error",
    "cross_doc_mismatch",
  ].includes(status);

  const why =
    status === "fail"
      ? failRejectionLanguage(rule).text
      : reviewLike
        ? rule.verifyQuestion || rule.message || "This rule needs a reviewer decision."
        : rule.message || "The rule evidence is shown for traceability.";

  // Nothing was located — show only the explanation, no empty comparison grid.
  if (model.mode === "none") {
    return (
      <div className="rounded-lg border border-white/10 bg-[#0B0F14]/45 p-2.5">
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <span className="rounded border border-white/10 bg-[#11161C] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">
            Evidence
          </span>
          <span className="text-[10px] text-slate-500">No value located for this rule</span>
        </div>
        <div className="rounded-md border border-amber-500/25 bg-amber-950/15 px-2.5 py-2 text-xs leading-relaxed text-amber-200">
          {why}
        </div>
      </div>
    );
  }

  // For each source, the tokens to compare against = the union of all *other*
  // sources' tokens. Single-document mode yields empty sets (no highlighting).
  const tokenSets = model.sources.map(
    s => new Set(tokenize(s.value).map(normalizeToken).filter(Boolean))
  );
  const compareSets = model.sources.map((_, i) => {
    if (model.mode !== "compare") return new Set<string>();
    const union = new Set<string>();
    tokenSets.forEach((set, j) => {
      if (j !== i) set.forEach(t => union.add(t));
    });
    return union;
  });

  return (
    <div className="rounded-lg border border-white/10 bg-[#0B0F14]/45 p-2.5">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <span className="rounded border border-white/10 bg-[#11161C] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">
          Evidence
        </span>
        <span className="text-[10px] text-slate-400">{model.headline}</span>
      </div>

      <div className={`grid gap-2 ${model.sources.length >= 2 ? "grid-cols-2" : "grid-cols-1"}`}>
        {model.sources.map((source, i) => (
          <EvidencePanel
            key={`${source.document}-${i}`}
            source={source}
            compareTo={compareSets[i]}
            showMeta={source.page != null || source.confidence != null}
          />
        ))}
      </div>

      <div className="mt-2 rounded-md border border-amber-500/25 bg-amber-950/15 px-2.5 py-2 text-xs leading-relaxed text-amber-200">
        {why}
      </div>
    </div>
  );
}

export default EvidenceCompare;

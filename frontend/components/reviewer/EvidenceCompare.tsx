"use client";
import React from "react";
import type { QCRuleResult } from "@/lib/api";

function tokenize(value: string): string[] {
  return value.split(/(\s+|[,;:()[\]{}]+)/).filter(token => token.length > 0);
}

function normalizeToken(value: string): string {
  return value.trim().toLowerCase().replace(/^[^\w.%-]+|[^\w.%-]+$/g, "");
}

function EvidenceValue({
  title,
  value,
  compareTo,
  tone,
}: {
  title: string;
  value: string;
  compareTo: string;
  tone: "found" | "expected";
}) {
  const compareTokens = new Set(tokenize(compareTo).map(normalizeToken).filter(Boolean));
  const titleColor = tone === "found" ? "text-slate-500" : "text-slate-400";
  const valueColor = tone === "found" ? "text-slate-300" : "text-slate-200";
  return (
    <div
      className={`rounded-lg p-2.5 ${tone === "found" ? "border border-white/10 bg-[#11161C]/80" : "border border-slate-500/25 bg-slate-950/25"}`}
    >
      <div className={`mb-1 text-[10px] font-semibold uppercase tracking-wide ${titleColor}`}>
        {title}
      </div>
      <div className={`font-mono text-xs leading-relaxed ${valueColor}`}>
        {value ? (
          tokenize(value).map((token, index) => {
            const normalized = normalizeToken(token);
            const mismatch = Boolean(normalized) && !compareTokens.has(normalized);
            return (
              <span
                key={`${token}-${index}`}
                className={
                  mismatch ? "rounded bg-amber-400/18 px-0.5 text-amber-200 ring-1 ring-amber-400/20" : undefined
                }
              >
                {token}
              </span>
            );
          })
        ) : (
          <span className="text-slate-600">No value extracted</span>
        )}
      </div>
    </div>
  );
}

export interface EvidenceCompareProps {
  rule: QCRuleResult;
  status: string;
}

export function EvidenceCompare({ rule, status }: EvidenceCompareProps) {
  const found = rule.appraisalValue ?? rule.extractedValue ?? "";
  const expected = rule.engagementValue ?? rule.expectedValue ?? "";
  const pageLabel =
    typeof rule.pdfPage === "number" && rule.pdfPage > 0
      ? `Page ${rule.pdfPage}`
      : "Page not located";
  const why =
    status === "fail"
      ? rule.rejectionText || rule.message || "The extracted report value does not satisfy this rule."
      : status === "verify"
        ? rule.verifyQuestion || rule.message || "This rule needs a reviewer decision."
        : rule.message || "The rule evidence is shown for traceability.";

  return (
    <div className="rounded-lg border border-white/10 bg-[#0B0F14]/45 p-2.5">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <span className="rounded border border-white/10 bg-[#11161C] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">
          Evidence
        </span>
        <span className="rounded border border-slate-500/25 bg-slate-950/30 px-1.5 py-0.5 text-[10px] text-slate-200">
          {pageLabel}
        </span>
        {rule.confidence != null && (
          <span className="rounded border border-white/10 bg-[#11161C] px-1.5 py-0.5 text-[10px] text-slate-400">
            Confidence {Math.round(Number(rule.confidence) * 100)}%
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <EvidenceValue title="Found in report" value={found} compareTo={expected} tone="found" />
        <EvidenceValue
          title="Expected from order"
          value={expected}
          compareTo={found}
          tone="expected"
        />
      </div>
      <div className="mt-2 rounded-md border border-amber-500/25 bg-amber-950/15 px-2.5 py-2 text-xs leading-relaxed text-amber-200">
        {why}
      </div>
    </div>
  );
}

export default EvidenceCompare;

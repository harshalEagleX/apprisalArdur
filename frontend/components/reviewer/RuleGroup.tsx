"use client";
import React, { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

/**
 * Collapsible wrapper for a rule that fired once per comparable (SCA-4 ×6, etc.).
 * The engine correctly produces one result per comp; this groups those identical-
 * titled results under a single header with a status roll-up so the reviewer sees
 * one row, not six. The per-comp results (full RuleCards, each independently
 * actionable) are the children. Groups that need attention open by default.
 */
export interface RuleGroupProps {
  ruleId: string;
  ruleName?: string;
  count: number;
  fail: number;
  review: number;
  pass: number;
  defaultOpen: boolean;
  children: React.ReactNode;
}

export function RuleGroup({ ruleId, ruleName, count, fail, review, pass, defaultOpen, children }: RuleGroupProps) {
  // `open` follows defaultOpen (attention/focus) until the reviewer explicitly
  // toggles, after which their choice wins. Derived state — no effect — so the
  // group never fights a manual collapse and we avoid set-state-in-effect.
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const open = userOpen ?? defaultOpen;
  const attention = fail + review;
  const summary = [
    fail ? `${fail} fail` : "",
    review ? `${review} review` : "",
    pass ? `${pass} pass` : "",
  ].filter(Boolean).join(" · ");

  return (
    <div
      className={`rounded-lg border ${attention ? "border-amber-500/20 bg-amber-950/[0.06]" : "border-white/8 bg-white/[0.02]"}`}
    >
      <button
        onClick={() => setUserOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
        aria-expanded={open}
      >
        <span className="font-mono text-[10px] bg-[#0B0F14]/70 border border-white/10 px-1.5 py-0.5 rounded text-slate-400 flex-shrink-0">
          {ruleId}
        </span>
        <span className="text-xs font-medium text-slate-300 flex-1 min-w-0 truncate">
          {ruleName ? `${ruleName} (${count} comparables)` : `${count} comparables`}
        </span>
        <span
          className={`text-[10px] flex-shrink-0 ${attention ? "text-amber-300" : "text-slate-600"}`}
        >
          {summary}
        </span>
        <span className="flex-shrink-0 text-slate-600">
          {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </span>
      </button>
      {open && <div className="px-2 pb-2 space-y-2">{children}</div>}
    </div>
  );
}

export default RuleGroup;

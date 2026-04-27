"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { QCResults, RuleResult } from "@/lib/legacy-types";

type Props = {
  results: QCResults;
  filename: string;
  onRuleClick: (rule: RuleResult) => void;
};

const STATUS_CONFIG: Record<string, { icon: string; color: string; bg: string; border: string }> = {
  pass:    { icon: "✅", color: "text-green-700", bg: "bg-green-50",  border: "border-green-200" },
  fail:    { icon: "❌", color: "text-red-700",   bg: "bg-red-50",    border: "border-red-200" },
  verify:  { icon: "⚠️", color: "text-amber-700", bg: "bg-amber-50",  border: "border-amber-200" },
  warning: { icon: "🔔", color: "text-orange-700",bg: "bg-orange-50", border: "border-orange-200" },
  skipped: { icon: "⏭️", color: "text-slate-400", bg: "bg-slate-50",  border: "border-slate-200" },
};

const SEVERITY_BADGE: Record<string, string> = {
  BLOCKING: "bg-red-100 text-red-700",
  STANDARD: "bg-blue-100 text-blue-700",
  ADVISORY: "bg-slate-100 text-slate-600",
};

function ConfBar({ value }: { value?: number }) {
  if (value === undefined) return null;
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500";
  return (
    <span className="inline-flex items-center gap-1 ml-2">
      <span className="w-16 h-1.5 rounded-full bg-slate-200 inline-block overflow-hidden">
        <span className={`h-full ${color} block`} style={{ width: `${pct}%` }} />
      </span>
      <span className="text-xs text-slate-400">{pct}%</span>
    </span>
  );
}

function RuleRow({ rule, onClick }: { rule: RuleResult; onClick: () => void }) {
  const cfg = STATUS_CONFIG[rule.status] ?? STATUS_CONFIG.skipped;
  const actionable = rule.status === "fail" || rule.status === "verify";

  return (
    <button
      onClick={onClick}
      className={`
        w-full text-left p-3 rounded-lg border transition-all
        ${cfg.bg} ${cfg.border}
        ${actionable ? "hover:shadow-sm hover:scale-[1.005] cursor-pointer" : "cursor-default"}
      `}
    >
      <div className="flex items-start gap-2">
        <span className="text-base mt-0.5 flex-shrink-0">{cfg.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs font-bold text-slate-500">[{rule.rule_id}]</span>
            <span className={`text-sm font-medium ${cfg.color}`}>{rule.rule_name}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${SEVERITY_BADGE[rule.severity] ?? SEVERITY_BADGE.STANDARD}`}>
              {rule.severity}
            </span>
            {rule.source_page && (
              <span className="text-xs text-slate-400">page {rule.source_page}</span>
            )}
            <ConfBar value={rule.field_confidence ?? undefined} />
          </div>
          <p className="text-sm text-slate-600 mt-0.5 line-clamp-2">{rule.message}</p>
          {actionable && (
            <p className="text-xs text-blue-500 mt-1">Click to review details →</p>
          )}
        </div>
      </div>
    </button>
  );
}

export default function ResultsDashboard({ results, filename, onRuleClick }: Props) {
  const address = [
    results.extracted_fields?.property_address,
    results.extracted_fields?.city,
    results.extracted_fields?.state,
    results.extracted_fields?.zip_code,
  ].filter(Boolean).join(", ");

  const fails    = results.rule_results.filter(r => r.status === "fail");
  const verifies = results.rule_results.filter(r => r.status === "verify" || r.status === "warning");
  const passes   = results.rule_results.filter(r => r.status === "pass");
  const skipped  = results.rule_results.filter(r => r.status === "skipped");

  const secs = (results.processing_time_ms / 1000).toFixed(1);

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardContent className="pt-5">
          <div className="flex flex-wrap gap-4 items-start">
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-bold text-slate-900 truncate">
                {address || filename}
              </h2>
              <div className="flex flex-wrap gap-3 mt-1 text-sm text-slate-500">
                <span>⏱ {secs}s</span>
                <span>📄 {results.total_pages} pages</span>
                <span>🔍 {results.extraction_method}</span>
                {results.cache_hit && <Badge variant="outline" className="text-xs">Cache hit</Badge>}
              </div>
            </div>

            {/* Score summary */}
            <div className="flex gap-4 text-center">
              <div className="bg-green-50 rounded-lg px-4 py-2">
                <div className="text-2xl font-bold text-green-700">{results.passed}</div>
                <div className="text-xs text-green-600">PASSED</div>
              </div>
              <div className="bg-red-50 rounded-lg px-4 py-2">
                <div className="text-2xl font-bold text-red-700">{results.failed}</div>
                <div className="text-xs text-red-600">FAILED</div>
              </div>
              <div className="bg-amber-50 rounded-lg px-4 py-2">
                <div className="text-2xl font-bold text-amber-700">{results.verify}</div>
                <div className="text-xs text-amber-600">VERIFY</div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Failed rules — most important */}
      {fails.length > 0 && (
        <Card className="border-red-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-red-700 text-base flex items-center gap-2">
              ❌ Failed Rules — Action Required ({fails.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {fails.map(r => <RuleRow key={r.rule_id} rule={r} onClick={() => onRuleClick(r)} />)}
          </CardContent>
        </Card>
      )}

      {/* Verify / Warning rules */}
      {verifies.length > 0 && (
        <Card className="border-amber-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-amber-700 text-base flex items-center gap-2">
              ⚠️ Needs Human Review ({verifies.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {verifies.map(r => <RuleRow key={r.rule_id} rule={r} onClick={() => onRuleClick(r)} />)}
          </CardContent>
        </Card>
      )}

      {/* Passed rules — collapsed */}
      {passes.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer select-none flex items-center gap-2 text-green-700 font-medium text-sm list-none">
            <span className="group-open:rotate-90 transition-transform inline-block">▶</span>
            ✅ Passed Rules ({passes.length})
          </summary>
          <Card className="mt-2 border-green-200">
            <CardContent className="pt-4 space-y-2">
              {passes.map(r => <RuleRow key={r.rule_id} rule={r} onClick={() => onRuleClick(r)} />)}
            </CardContent>
          </Card>
        </details>
      )}

      {/* Skipped */}
      {skipped.length > 0 && (
        <div className="text-xs text-slate-400 text-center">
          {skipped.length} rules skipped (not applicable to this document type)
        </div>
      )}
    </div>
  );
}

"use client";

import { useState } from "react";
import UploadScreen from "@/components/UploadScreen";
import ResultsDashboard from "@/components/ResultsDashboard";
import RuleDetailView from "@/components/RuleDetailView";

export type RuleResult = {
  rule_id: string;
  rule_name: string;
  status: string;
  message: string;
  action_item?: string;
  appraisal_value?: string;
  engagement_value?: string;
  review_required: boolean;
  severity: string;
  source_page?: number;
  field_confidence?: number;
};

export type QCResults = {
  success: boolean;
  processing_time_ms: number;
  total_pages: number;
  extraction_method: string;
  total_rules: number;
  passed: number;
  failed: number;
  verify: number;
  document_id?: string;
  cache_hit: boolean;
  file_hash: string;
  extracted_fields: Record<string, unknown>;
  field_confidence: Record<string, number>;
  rule_results: RuleResult[];
  action_items: string[];
};

type Screen = "upload" | "results" | "detail";

export default function Home() {
  const [screen, setScreen] = useState<Screen>("upload");
  const [results, setResults] = useState<QCResults | null>(null);
  const [selectedRule, setSelectedRule] = useState<RuleResult | null>(null);
  const [filename, setFilename] = useState("");

  const handleResults = (data: QCResults, name: string) => {
    setResults(data);
    setFilename(name);
    setScreen("results");
  };

  return (
    <main className="min-h-screen bg-slate-50">
      <nav className="bg-white border-b border-slate-200 px-6 py-3 flex items-center gap-3">
        <div className="w-8 h-8 bg-blue-600 rounded flex items-center justify-center text-white font-bold text-sm">
          QC
        </div>
        <span className="font-semibold text-slate-800">Appraisal QC</span>
        {screen !== "upload" && (
          <button
            onClick={() => { setScreen("upload"); setResults(null); }}
            className="ml-auto text-sm text-slate-500 hover:text-blue-600 transition-colors"
          >
            ← New Upload
          </button>
        )}
      </nav>

      <div className="max-w-5xl mx-auto px-4 py-8">
        {screen === "upload" && (
          <UploadScreen onResults={handleResults} />
        )}
        {screen === "results" && results && (
          <ResultsDashboard
            results={results}
            filename={filename}
            onRuleClick={(rule) => { setSelectedRule(rule); setScreen("detail"); }}
          />
        )}
        {screen === "detail" && selectedRule && results && (
          <RuleDetailView
            rule={selectedRule}
            results={results}
            onBack={() => setScreen("results")}
          />
        )}
      </div>
    </main>
  );
}

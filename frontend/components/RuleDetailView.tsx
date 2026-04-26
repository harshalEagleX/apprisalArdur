"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import type { QCResults, RuleResult } from "@/app/page";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5001";

type FeedbackType = "CORRECT" | "OCR_ERROR" | "EXTRACTION_ERROR" | "RULE_ERROR";

type Props = {
  rule: RuleResult;
  results: QCResults;
  onBack: () => void;
};

const FEEDBACK_OPTIONS: { type: FeedbackType; label: string; desc: string }[] = [
  { type: "CORRECT",          label: "✓ Yes, this is a real error",         desc: "Send back to appraiser." },
  { type: "OCR_ERROR",        label: "🔤 No — OCR misread a word",          desc: "The system misread the text. Enter the correct value below." },
  { type: "EXTRACTION_ERROR", label: "🧩 No — System extracted wrong field", desc: "System pulled the wrong value. Enter the correct value below." },
  { type: "RULE_ERROR",       label: "⚙️ No — The rule logic is wrong",      desc: "This rule fired incorrectly. Add a comment." },
];

export default function RuleDetailView({ rule, results, onBack }: Props) {
  const [feedbackType, setFeedbackType] = useState<FeedbackType | null>(null);
  const [correctedValue, setCorrectedValue] = useState("");
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const confidence = rule.field_confidence;
  const confPct = confidence !== undefined ? Math.round(confidence * 100) : null;
  const confColor = confPct === null ? "" : confPct >= 80 ? "text-green-600" : confPct >= 50 ? "text-amber-600" : "text-red-600";

  const submitFeedback = async () => {
    if (!feedbackType || !results.document_id) return;
    setSubmitting(true);
    try {
      const body = {
        document_id: results.document_id,
        rule_id: rule.rule_id,
        field_name: rule.rule_id,
        original_value: rule.appraisal_value || rule.message,
        corrected_value: correctedValue || undefined,
        feedback_type: feedbackType,
        operator_comment: comment || undefined,
      };
      await fetch(`${API}/qc/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setSubmitted(true);
    } catch {
      alert("Failed to save feedback. Please try again.");
    }
    setSubmitting(false);
  };

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-sm text-slate-500 hover:text-blue-600 flex items-center gap-1">
        ← Back to Results
      </button>

      {/* Rule header */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm bg-slate-100 px-2 py-1 rounded font-bold">{rule.rule_id}</span>
            <CardTitle className="text-base">{rule.rule_name}</CardTitle>
            <span className={`text-xs px-2 py-0.5 rounded font-medium uppercase
              ${rule.status === "fail" ? "bg-red-100 text-red-700" :
                rule.status === "verify" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600"}`}>
              {rule.status}
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-slate-700">{rule.message}</p>

          {/* Side-by-side comparison */}
          {(rule.appraisal_value || rule.engagement_value) && (
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-50 rounded-lg p-3 border">
                <div className="text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wide">
                  Found in Report
                </div>
                <div className="font-mono text-sm text-slate-800 break-all">
                  {rule.appraisal_value || "—"}
                </div>
                {rule.source_page && (
                  <div className="text-xs text-slate-400 mt-1">Page {rule.source_page}</div>
                )}
                {confPct !== null && (
                  <div className={`text-xs mt-1 font-medium ${confColor}`}>
                    Confidence: {confPct}%
                  </div>
                )}
              </div>
              <div className="bg-blue-50 rounded-lg p-3 border border-blue-200">
                <div className="text-xs font-semibold text-blue-500 mb-1 uppercase tracking-wide">
                  Expected (Order Form)
                </div>
                <div className="font-mono text-sm text-blue-800 break-all">
                  {rule.engagement_value || "—"}
                </div>
              </div>
            </div>
          )}

          {rule.action_item && (
            <div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm text-amber-800">
              <span className="font-semibold">Action required: </span>{rule.action_item}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Feedback — Phase 5 / Phase 6 learning loop */}
      {results.document_id && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Reviewer Feedback</CardTitle>
            <p className="text-xs text-slate-500">
              Your response trains the system — it will be right next time.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            {submitted ? (
              <div className="bg-green-50 border border-green-200 rounded p-4 text-green-700 text-center font-medium">
                ✓ Feedback recorded. Thank you!
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 gap-2">
                  {FEEDBACK_OPTIONS.map(opt => (
                    <button
                      key={opt.type}
                      onClick={() => setFeedbackType(opt.type)}
                      className={`text-left p-3 rounded-lg border transition-all text-sm
                        ${feedbackType === opt.type
                          ? "border-blue-500 bg-blue-50"
                          : "border-slate-200 hover:border-blue-300 bg-white"
                        }`}
                    >
                      <div className="font-medium">{opt.label}</div>
                      <div className="text-slate-500 text-xs mt-0.5">{opt.desc}</div>
                    </button>
                  ))}
                </div>

                {feedbackType && feedbackType !== "CORRECT" && (
                  <div className="space-y-3 pt-2">
                    <Separator />
                    {(feedbackType === "OCR_ERROR" || feedbackType === "EXTRACTION_ERROR") && (
                      <div>
                        <Label htmlFor="corrected" className="text-sm">Correct value</Label>
                        <Textarea
                          id="corrected"
                          placeholder="Enter what it should say..."
                          value={correctedValue}
                          onChange={e => setCorrectedValue(e.target.value)}
                          className="mt-1 text-sm"
                          rows={2}
                        />
                      </div>
                    )}
                    <div>
                      <Label htmlFor="comment" className="text-sm">Comment (optional)</Label>
                      <Textarea
                        id="comment"
                        placeholder="Additional context..."
                        value={comment}
                        onChange={e => setComment(e.target.value)}
                        className="mt-1 text-sm"
                        rows={2}
                      />
                    </div>
                  </div>
                )}

                {feedbackType && (
                  <Button
                    onClick={submitFeedback}
                    disabled={submitting}
                    className="w-full"
                  >
                    {submitting ? "Saving..." : "Submit Feedback"}
                  </Button>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

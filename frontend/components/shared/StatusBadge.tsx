const CONFIG: Record<string, { label: string; dot: string; text: string; bg: string; border: string }> = {
  UPLOADED:          { label: "Uploaded",         dot: "bg-slate-400",  text: "text-slate-300",  bg: "bg-[#161B22]", border: "border-white/10" },
  VALIDATING:        { label: "Validating",       dot: "bg-slate-400 animate-pulse", text: "text-slate-200", bg: "bg-slate-950/40", border: "border-slate-500/25" },
  VALIDATION_FAILED: { label: "Invalid",          dot: "bg-red-400",    text: "text-red-200",    bg: "bg-red-950/40", border: "border-red-500/25" },
  QC_PROCESSING:     { label: "QC Running",       dot: "bg-slate-400 animate-pulse", text: "text-slate-200", bg: "bg-slate-950/40", border: "border-slate-500/25" },
  REVIEW_PENDING:    { label: "Awaiting Review",  dot: "bg-amber-400",  text: "text-amber-200",  bg: "bg-amber-950/40", border: "border-amber-500/25" },
  IN_REVIEW:         { label: "In Review",        dot: "bg-amber-400",  text: "text-amber-200",  bg: "bg-amber-950/40", border: "border-amber-500/25" },
  PENDING:           { label: "Pending",          dot: "bg-slate-500",  text: "text-slate-400",  bg: "bg-[#161B22]", border: "border-white/10" },
  PROCESSING:        { label: "Processing",       dot: "bg-slate-400 animate-pulse", text: "text-slate-300", bg: "bg-slate-950/40", border: "border-slate-500/25" },
  COMPLETED:         { label: "Completed",        dot: "bg-green-400",  text: "text-green-200",  bg: "bg-green-950/40", border: "border-green-500/25" },
  ERROR:             { label: "Error",            dot: "bg-red-400",    text: "text-red-200",    bg: "bg-red-950/40", border: "border-red-500/25" },
  DISMISSED:         { label: "Dismissed",        dot: "bg-slate-600",  text: "text-slate-500",  bg: "bg-[#161B22]", border: "border-white/[0.06]" },
  NEEDS_ASSIGNMENT:  { label: "Needs Assignment", dot: "bg-orange-400", text: "text-orange-200", bg: "bg-orange-950/40", border: "border-orange-500/25" },
  // Order documentStatus badges (OrderDocumentStatus — QC_PROCESSING/COMPLETED/ERROR share the batch config above)
  INCOMPLETE:   { label: "Incomplete",    dot: "bg-slate-500",  text: "text-slate-400",  bg: "bg-[#161B22]", border: "border-white/10" },
  UNMATCHED:    { label: "Unmatched",     dot: "bg-orange-400", text: "text-orange-200", bg: "bg-orange-950/40", border: "border-orange-500/25" },
  READY_FOR_QC: { label: "Ready for QC",  dot: "bg-slate-400",  text: "text-slate-300",  bg: "bg-slate-950/40", border: "border-slate-500/25" },
  NEEDS_REVIEW: { label: "Needs Review",  dot: "bg-amber-400",  text: "text-amber-200",  bg: "bg-amber-950/40", border: "border-amber-500/25" },
  // QC decision badges
  AUTO_PASS:  { label: "Auto Pass",    dot: "bg-green-400", text: "text-green-200", bg: "bg-green-950/40", border: "border-green-500/25" },
  TO_VERIFY:  { label: "Needs Review", dot: "bg-amber-400", text: "text-amber-200", bg: "bg-amber-950/40", border: "border-amber-500/25" },
  AUTO_FAIL:  { label: "Failed",       dot: "bg-red-400",   text: "text-red-200",   bg: "bg-red-950/40", border: "border-red-500/25" },
  BLOCKED:    { label: "Blocked",      dot: "bg-red-400",   text: "text-red-200",   bg: "bg-red-950/50", border: "border-red-500/35" },
  // Rule statuses
  pass:        { label: "Pass",   dot: "bg-green-400", text: "text-green-200", bg: "bg-green-950/40", border: "border-green-500/25" },
  fail:        { label: "Fail",   dot: "bg-red-400",   text: "text-red-200",   bg: "bg-red-950/40", border: "border-red-500/25" },
  verify:      { label: "Review", dot: "bg-amber-400", text: "text-amber-200", bg: "bg-amber-950/40", border: "border-amber-500/25" },
  review:      { label: "Review", dot: "bg-amber-400", text: "text-amber-200", bg: "bg-amber-950/40", border: "border-amber-500/25" },
  extraction_failed: { label: "Extraction Failed", dot: "bg-amber-400", text: "text-amber-200", bg: "bg-amber-950/40", border: "border-amber-500/25" },
  ocr_low_confidence: { label: "Low OCR Confidence", dot: "bg-amber-400", text: "text-amber-200", bg: "bg-amber-950/40", border: "border-amber-500/25" },
  system_error: { label: "System Error", dot: "bg-red-400", text: "text-red-200", bg: "bg-red-950/40", border: "border-red-500/25" },
  source_missing: { label: "Source Missing", dot: "bg-amber-400", text: "text-amber-200", bg: "bg-amber-950/40", border: "border-amber-500/25" },
  cross_doc_mismatch: { label: "Cross-Doc Mismatch", dot: "bg-red-400", text: "text-red-200", bg: "bg-red-950/40", border: "border-red-500/25" },
  not_executed: { label: "Not Executed", dot: "bg-slate-400", text: "text-slate-300", bg: "bg-[#161B22]", border: "border-white/10" },
  not_applicable: { label: "Not Applicable", dot: "bg-slate-400", text: "text-slate-300", bg: "bg-[#161B22]", border: "border-white/10" },
  MANUAL_PASS: { label: "Passed", dot: "bg-green-400", text: "text-green-200", bg: "bg-green-950/40", border: "border-green-500/25" },
};

const FALLBACK = { label: "", dot: "bg-slate-400", text: "text-slate-400", bg: "bg-[#161B22]", border: "border-white/10" };

export default function StatusBadge({ status, size = "sm" }: { status: string; size?: "sm" | "xs" }) {
  const normalizedStatus = status === "MANUAL_PASS" ? status : status.toLowerCase();
  const c = CONFIG[status] ?? CONFIG[normalizedStatus] ?? { ...FALLBACK, label: status.replace(/_/g, " ") };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 font-medium border ${c.border} ${c.bg} ${c.text} ${size === "xs" ? "text-[10px]" : "text-xs"}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${c.dot}`} />
      {c.label}
    </span>
  );
}

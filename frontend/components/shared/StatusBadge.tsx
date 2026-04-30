const CONFIG: Record<string, { label: string; dot: string; text: string; bg: string }> = {
  UPLOADED:          { label: "Uploaded",         dot: "bg-slate-400",  text: "text-slate-300",  bg: "bg-slate-800/60" },
  VALIDATING:        { label: "Validating",        dot: "bg-blue-400 animate-pulse", text: "text-blue-300",  bg: "bg-blue-950/50" },
  VALIDATION_FAILED: { label: "Invalid",           dot: "bg-red-400",    text: "text-red-300",    bg: "bg-red-950/50" },
  QC_PROCESSING:     { label: "QC Running",        dot: "bg-indigo-400 animate-pulse", text: "text-indigo-300", bg: "bg-indigo-950/50" },
  REVIEW_PENDING:    { label: "Awaiting Review",   dot: "bg-amber-400",  text: "text-amber-300",  bg: "bg-amber-950/50" },
  IN_REVIEW:         { label: "In Review",         dot: "bg-orange-400", text: "text-orange-300", bg: "bg-orange-950/50" },
  COMPLETED:         { label: "Completed",         dot: "bg-green-400",  text: "text-green-300",  bg: "bg-green-950/50" },
  ERROR:             { label: "Error",             dot: "bg-red-400",    text: "text-red-300",    bg: "bg-red-950/50" },
  // QC decision badges
  AUTO_PASS:  { label: "Auto Pass",   dot: "bg-green-400",  text: "text-green-300",  bg: "bg-green-950/50" },
  TO_VERIFY:  { label: "Needs Review",dot: "bg-amber-400",  text: "text-amber-300",  bg: "bg-amber-950/50" },
  AUTO_FAIL:  { label: "Failed",      dot: "bg-red-400",    text: "text-red-300",    bg: "bg-red-950/50" },
  // Rule statuses
  pass:    { label: "Pass",    dot: "bg-green-400",  text: "text-green-300",  bg: "bg-green-950/50" },
  fail:    { label: "Fail",    dot: "bg-red-400",    text: "text-red-300",    bg: "bg-red-950/50" },
  verify:  { label: "Review",  dot: "bg-amber-400",  text: "text-amber-300",  bg: "bg-amber-950/50" },
  warning: { label: "Warning", dot: "bg-orange-400", text: "text-orange-300", bg: "bg-orange-950/50" },
  skipped: { label: "Skipped", dot: "bg-slate-400",  text: "text-slate-400",  bg: "bg-slate-800/50" },
  MANUAL_PASS: { label: "Accepted",  dot: "bg-teal-400",   text: "text-teal-300",   bg: "bg-teal-950/50" },
};

const FALLBACK = { label: "", dot: "bg-slate-400", text: "text-slate-400", bg: "bg-slate-800/50" };

export default function StatusBadge({ status, size = "sm" }: { status: string; size?: "sm" | "xs" }) {
  const normalizedStatus = status === "MANUAL_PASS" ? status : status.toLowerCase();
  const c = CONFIG[status] ?? CONFIG[normalizedStatus] ?? { ...FALLBACK, label: status.replace(/_/g, " ") };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 font-medium border border-transparent ${c.bg} ${c.text} ${size === "xs" ? "text-[10px]" : "text-xs"}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${c.dot}`} />
      {c.label}
    </span>
  );
}

const CONFIG: Record<string, { label: string; dot: string; text: string; bg: string; border: string }> = {
  UPLOADED:          { label: "Uploaded",         dot: "bg-slate-400",  text: "text-slate-300",  bg: "bg-[#161B22]", border: "border-white/10" },
  VALIDATING:        { label: "Validating",       dot: "bg-blue-400 animate-pulse", text: "text-blue-200", bg: "bg-blue-950/40", border: "border-blue-500/25" },
  VALIDATION_FAILED: { label: "Invalid",          dot: "bg-red-400",    text: "text-red-200",    bg: "bg-red-950/40", border: "border-red-500/25" },
  QC_PROCESSING:     { label: "QC Running",       dot: "bg-blue-400 animate-pulse", text: "text-blue-200", bg: "bg-blue-950/40", border: "border-blue-500/25" },
  REVIEW_PENDING:    { label: "Awaiting Review",  dot: "bg-amber-400",  text: "text-amber-200",  bg: "bg-amber-950/40", border: "border-amber-500/25" },
  IN_REVIEW:         { label: "In Review",        dot: "bg-amber-400",  text: "text-amber-200",  bg: "bg-amber-950/40", border: "border-amber-500/25" },
  COMPLETED:         { label: "Completed",        dot: "bg-green-400",  text: "text-green-200",  bg: "bg-green-950/40", border: "border-green-500/25" },
  ERROR:             { label: "Error",            dot: "bg-red-400",    text: "text-red-200",    bg: "bg-red-950/40", border: "border-red-500/25" },
  // QC decision badges
  AUTO_PASS:  { label: "Auto Pass",    dot: "bg-green-400", text: "text-green-200", bg: "bg-green-950/40", border: "border-green-500/25" },
  TO_VERIFY:  { label: "Needs Review", dot: "bg-amber-400", text: "text-amber-200", bg: "bg-amber-950/40", border: "border-amber-500/25" },
  AUTO_FAIL:  { label: "Failed",       dot: "bg-red-400",   text: "text-red-200",   bg: "bg-red-950/40", border: "border-red-500/25" },
  // Rule statuses
  pass:        { label: "Pass",   dot: "bg-green-400", text: "text-green-200", bg: "bg-green-950/40", border: "border-green-500/25" },
  fail:        { label: "Fail",   dot: "bg-red-400",   text: "text-red-200",   bg: "bg-red-950/40", border: "border-red-500/25" },
  verify:      { label: "Review", dot: "bg-amber-400", text: "text-amber-200", bg: "bg-amber-950/40", border: "border-amber-500/25" },
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

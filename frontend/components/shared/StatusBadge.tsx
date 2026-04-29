const STYLES: Record<string, string> = {
  UPLOADED:          "bg-slate-700 text-slate-300",
  VALIDATING:        "bg-blue-900 text-blue-300",
  VALIDATION_FAILED: "bg-red-900 text-red-300",
  QC_PROCESSING:     "bg-indigo-900 text-indigo-300",
  REVIEW_PENDING:    "bg-amber-900 text-amber-300",
  IN_REVIEW:         "bg-orange-900 text-orange-300",
  COMPLETED:         "bg-green-900 text-green-300",
  ERROR:             "bg-red-900 text-red-300",
};

export default function StatusBadge({ status }: { status: string }) {
  const cls = STYLES[status] ?? "bg-slate-700 text-slate-300";
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded ${cls}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

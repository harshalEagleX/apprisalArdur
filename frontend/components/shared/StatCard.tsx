import { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: number | string;
  icon?: LucideIcon;
  trend?: "up" | "down" | "neutral";
  color?: "blue" | "green" | "amber" | "red" | "indigo" | "slate";
  loading?: boolean;
}

const COLORS = {
  blue:   "text-slate-200   bg-slate-950/30   border-slate-500/25",
  green:  "text-green-200  bg-green-950/30  border-green-500/25",
  amber:  "text-amber-200  bg-amber-950/30  border-amber-500/25",
  red:    "text-red-200    bg-red-950/30    border-red-500/25",
  indigo: "text-slate-200   bg-slate-950/30   border-slate-500/25",
  slate:  "text-slate-200  bg-[#11161C]     border-white/10",
};

export default function StatCard({ label, value, icon: Icon, color = "slate", loading }: StatCardProps) {
  const c = COLORS[color];
  return (
    <div className={`h-full min-w-0 rounded-lg border p-4 shadow-[0_12px_32px_rgba(0,0,0,0.18)] ${c}`}>
      <div className="flex items-start justify-between mb-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide opacity-70">{label}</span>
        {Icon && <Icon size={14} className="opacity-50 mt-0.5" />}
      </div>
      {loading ? (
        <div className="h-8 w-16 bg-current opacity-10 rounded animate-pulse" />
      ) : (
        <div className="text-2xl font-semibold tabular-nums tracking-normal">{value}</div>
      )}
    </div>
  );
}

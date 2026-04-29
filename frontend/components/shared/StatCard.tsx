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
  blue:   "text-blue-400   bg-blue-950/50   border-blue-900/50",
  green:  "text-green-400  bg-green-950/50  border-green-900/50",
  amber:  "text-amber-400  bg-amber-950/50  border-amber-900/50",
  red:    "text-red-400    bg-red-950/50    border-red-900/50",
  indigo: "text-indigo-400 bg-indigo-950/50 border-indigo-900/50",
  slate:  "text-slate-300  bg-slate-800/50  border-slate-700/50",
};

export default function StatCard({ label, value, icon: Icon, color = "slate", loading }: StatCardProps) {
  const c = COLORS[color];
  return (
    <div className={`rounded-xl border p-4 ${c}`}>
      <div className="flex items-start justify-between mb-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider opacity-70">{label}</span>
        {Icon && <Icon size={14} className="opacity-50 mt-0.5" />}
      </div>
      {loading ? (
        <div className="h-8 w-16 bg-current opacity-10 rounded animate-pulse" />
      ) : (
        <div className="text-2xl font-bold tabular-nums">{value}</div>
      )}
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: number | string;
  color?: string;
  sub?: string;
}

export default function StatCard({ label, value, color = "text-blue-400", sub }: StatCardProps) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <div className={`text-2xl font-bold tabular-nums ${color}`}>{value}</div>
      <div className="text-slate-400 text-sm mt-1">{label}</div>
      {sub && <div className="text-slate-600 text-xs mt-0.5">{sub}</div>}
    </div>
  );
}

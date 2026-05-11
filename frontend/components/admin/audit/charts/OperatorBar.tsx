"use client";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";

interface Operator {
  name: string;
  activeMinutes: number;
  filesProcessed: number;
  corrections: number;
}

interface Props {
  data: Operator[];
}

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-slate-900/95 px-3 py-2 text-xs shadow-xl">
      <p className="font-semibold text-slate-300 mb-1.5">{label}</p>
      {payload.map(p => (
        <div key={p.name} className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-slate-400">{p.name}:</span>
          <span className="text-white font-medium">{p.value.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
};

export default function OperatorBar({ data }: Props) {
  if (!data?.length) {
    return <div className="flex h-20 items-center justify-center text-xs text-slate-600">No operator data</div>;
  }

  // Truncate long names for the axis
  const formatted = data.slice(0, 8).map(op => ({
    ...op,
    name: op.name.split(" ")[0] ?? op.name,
  }));

  return (
    <ResponsiveContainer width="100%" height={140}>
      <BarChart data={formatted} margin={{ top: 4, right: 4, bottom: 0, left: -20 }} barSize={8}>
        <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" vertical={false} />
        <XAxis
          dataKey="name"
          tick={{ fill: "#64748b", fontSize: 9 }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fill: "#64748b", fontSize: 9 }}
          tickLine={false}
          axisLine={false}
          allowDecimals={false}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "#ffffff06" }} />
        <Legend
          wrapperStyle={{ fontSize: 9, paddingTop: 4 }}
          formatter={v => <span style={{ color: "#94a3b8" }}>{v}</span>}
        />
        <Bar dataKey="filesProcessed" name="Files"       fill="#6366f1" radius={[2, 2, 0, 0]} />
        <Bar dataKey="corrections"    name="Corrections" fill="#f59e0b" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

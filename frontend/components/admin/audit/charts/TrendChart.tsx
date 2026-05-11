"use client";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { TrendPoint } from "../types";

interface Props {
  data: TrendPoint[];
}

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-slate-900/95 px-3 py-2 text-xs shadow-xl">
      <p className="mb-1.5 font-semibold text-slate-300">{label}</p>
      {payload.map(p => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-slate-400">{p.name}:</span>
          <span className="font-medium text-white">{p.value.toFixed(1)}%</span>
        </div>
      ))}
    </div>
  );
};

export default function TrendChart({ data }: Props) {
  const formatted = data.map(d => ({
    ...d,
    date: new Date(d.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
  }));

  return (
    <ResponsiveContainer width="100%" height={160}>
      <LineChart data={formatted} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#ffffff0a" />
        <XAxis
          dataKey="date"
          tick={{ fill: "#64748b", fontSize: 9 }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: "#64748b", fontSize: 9 }}
          tickLine={false}
          axisLine={false}
          domain={[0, 100]}
          tickFormatter={v => `${v}%`}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          wrapperStyle={{ fontSize: 9, paddingTop: 4 }}
          formatter={v => <span style={{ color: "#94a3b8" }}>{v}</span>}
        />
        <Line
          type="monotone"
          dataKey="ocrAccuracy"
          name="OCR Accuracy"
          stroke="#6366f1"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 3, fill: "#6366f1" }}
        />
        <Line
          type="monotone"
          dataKey="passRate"
          name="Rule Pass Rate"
          stroke="#22c55e"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 3, fill: "#22c55e" }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

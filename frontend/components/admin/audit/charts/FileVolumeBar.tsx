"use client";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import type { TrendPoint } from "../types";

interface Props {
  data: TrendPoint[];
}

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-slate-900/95 px-3 py-2 text-xs shadow-xl">
      <p className="text-slate-300 font-semibold">{label}</p>
      <p className="text-indigo-300 mt-0.5">Files: <span className="text-white font-bold">{payload[0].value}</span></p>
    </div>
  );
};

export default function FileVolumeBar({ data }: Props) {
  const formatted = data.map(d => ({
    ...d,
    date: new Date(d.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
  }));

  return (
    <ResponsiveContainer width="100%" height={120}>
      <BarChart data={formatted} margin={{ top: 4, right: 8, bottom: 0, left: -20 }} barSize={6}>
        <CartesianGrid strokeDasharray="3 3" stroke="#ffffff0a" vertical={false} />
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
          allowDecimals={false}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "#ffffff06" }} />
        <Bar dataKey="fileCount" name="Files" fill="#6366f1" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

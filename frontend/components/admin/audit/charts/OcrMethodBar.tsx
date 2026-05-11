"use client";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

interface Method {
  method: string;
  count: number;
}

interface Props {
  data: Method[];
}

const METHOD_COLOR: Record<string, string> = {
  layout:    "#6366f1",
  embedded:  "#22c55e",
  tesseract: "#f59e0b",
  cloud:     "#06b6d4",
};

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-slate-900/95 px-3 py-2 text-xs shadow-xl">
      <p className="font-medium text-slate-300 capitalize">{label}</p>
      <p className="text-white font-bold">{payload[0].value.toLocaleString()} files</p>
    </div>
  );
};

export default function OcrMethodBar({ data }: Props) {
  if (!data?.length) {
    return <div className="flex h-20 items-center justify-center text-xs text-slate-600">No OCR data</div>;
  }

  const formatted = data.map(d => ({
    ...d,
    method: String(d.method ?? "unknown"),
    fill: METHOD_COLOR[String(d.method).toLowerCase()] ?? "#64748b",
  }));

  return (
    <ResponsiveContainer width="100%" height={120}>
      <BarChart data={formatted} margin={{ top: 4, right: 4, bottom: 0, left: -20 }} barSize={14}>
        <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" vertical={false} />
        <XAxis
          dataKey="method"
          tick={{ fill: "#64748b", fontSize: 9 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={v => String(v).slice(0, 8)}
        />
        <YAxis
          tick={{ fill: "#64748b", fontSize: 9 }}
          tickLine={false}
          axisLine={false}
          allowDecimals={false}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "#ffffff06" }} />
        {/* fill comes from each data item — no Cell needed */}
        <Bar dataKey="count" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

"use client";
import { PieChart, Pie, Tooltip, ResponsiveContainer } from "recharts";
import type { MlInsights } from "../types";

interface Props {
  data: MlInsights["decisionBreakdown"] | null;
}

// Colours paired directly into data items — recharts 3.x dropped Cell
const PALETTE = ["#22c55e", "#f59e0b", "#ef4444"];
const LABELS  = ["Auto Pass", "Needs Review", "Auto Fail"];

const CustomTooltip = ({ active, payload }: {
  active?: boolean;
  payload?: { name: string; value: number }[];
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-slate-900/95 px-3 py-2 text-xs shadow-xl">
      <p className="text-slate-300 font-medium">{payload[0].name}</p>
      <p className="text-white font-semibold">{payload[0].value.toFixed(1)}%</p>
    </div>
  );
};

export default function DecisionDonut({ data }: Props) {
  if (!data) return <EmptyState />;

  // Each slice carries its own fill — no Cell wrapper needed in recharts 3.x
  const slices = [
    { name: LABELS[0], value: data.autoPassPct,    count: data.autoPass,  fill: PALETTE[0] },
    { name: LABELS[1], value: data.needsReviewPct, count: data.toVerify,  fill: PALETTE[1] },
    { name: LABELS[2], value: data.autoFailPct,    count: data.autoFail,  fill: PALETTE[2] },
  ].filter(s => s.value > 0);

  return (
    <div className="flex items-center gap-3">
      <ResponsiveContainer width={100} height={100}>
        <PieChart>
          <Pie
            data={slices}
            cx="50%"
            cy="50%"
            innerRadius={28}
            outerRadius={44}
            dataKey="value"
            strokeWidth={0}
          />
          <Tooltip content={<CustomTooltip />} />
        </PieChart>
      </ResponsiveContainer>

      <div className="flex-1 space-y-1.5">
        {slices.map(s => (
          <div key={s.name} className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: s.fill }} />
              <span className="text-[10px] text-slate-400">{s.name}</span>
            </div>
            <div className="text-right">
              <span className="text-xs font-semibold text-white">{s.value.toFixed(0)}%</span>
              <span className="text-[10px] text-slate-600 ml-1">({s.count})</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-24 items-center justify-center text-xs text-slate-600">
      No decision data
    </div>
  );
}

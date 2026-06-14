"use client";
import { X, ExternalLink } from "lucide-react";
import type { GraphNode, GraphLink, ViewMode } from "./types";
import { NODE_COLOR, isSupportingPending } from "./types";

interface Props {
  node: GraphNode;
  links: GraphLink[];
  onClose: () => void;
  onDrillBatch: (id: number) => void;
  onDrillFile:  (id: string)  => void;
  onViewMode:   (m: ViewMode) => void;
}

// ── Status badge ──────────────────────────────────────────────────────────────
function StatusBadge({ status, fileType }: { status: string; fileType?: string }) {
  if (isSupportingPending(status, fileType)) {
    return (
      <span
        className="inline-flex items-center px-2 py-0.5 rounded border text-[10px] font-medium bg-slate-800 text-slate-400 border-slate-700"
        title="Supporting document — read for cross-document checks, not separately QC'd"
      >
        Supporting
      </span>
    );
  }
  const map: Record<string, string> = {
    PASS:           "bg-green-950 text-green-400 border-green-800/50",
    FAIL:           "bg-red-950 text-red-400 border-red-800/50",
    DONE:           "bg-cyan-950 text-cyan-400 border-cyan-800/50",
    COMPLETED:      "bg-green-950 text-green-400 border-green-800/50",
    REVIEW_PENDING: "bg-amber-950 text-amber-400 border-amber-800/50",
    QC_PROCESSING:  "bg-blue-950 text-blue-400 border-blue-800/50",
    UPLOADED:       "bg-slate-800 text-slate-300 border-slate-700",
    IN_REVIEW:      "bg-indigo-950 text-indigo-400 border-indigo-800/50",
    ERROR:          "bg-red-950 text-red-400 border-red-800/50",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] font-medium ${map[status] ?? "bg-slate-800 text-slate-400 border-slate-700"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

// ── Rule pass rate mini-bar ───────────────────────────────────────────────────
function RuleBar({ passed, failed, total }: { passed: number; failed: number; total: number }) {
  if (!total) return null;
  const pct = Math.round((passed / total) * 100);
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-slate-500">Rule results</span>
        <span className="text-[10px] text-slate-300 tabular-nums">{passed}/{total} passed ({pct}%)</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${pct}%`,
            background: pct > 70 ? "#22c55e" : pct > 40 ? "#f59e0b" : "#ef4444",
          }}
        />
      </div>
      {failed > 0 && (
        <p className="mt-0.5 text-[10px] text-red-400">{failed} failed</p>
      )}
    </div>
  );
}

// ── Format metadata value ─────────────────────────────────────────────────────
function fmtVal(key: string, val: string | number | null | undefined): string {
  if (val == null || val === "") return "—";
  const s = String(val);
  if ((key.toLowerCase().endsWith("at") || key.toLowerCase().endsWith("date")) && s.includes("T")) {
    try { return new Date(s).toLocaleString(); } catch { /* pass */ }
  }
  if (typeof val === "number" && key.toLowerCase().includes("ms")) {
    return `${(val / 1000).toFixed(2)}s`;
  }
  return s;
}

// ── Key label prettifier ──────────────────────────────────────────────────────
function prettyKey(key: string): string {
  return key.replace(/([A-Z])/g, " $1").replace(/^./, c => c.toUpperCase()).trim();
}

// ── Main drawer ───────────────────────────────────────────────────────────────
export default function AuditNodeDrawer({
  node, links, onClose, onDrillBatch, onDrillFile, onViewMode,
}: Props) {
  const color = NODE_COLOR[node.type as keyof typeof NODE_COLOR] ?? "#64748b";

  // Count directly connected nodes
  const connectedIds = new Set<string>();
  for (const l of links) {
    const src = typeof l.source === "string" ? l.source : (l.source as GraphNode).id;
    const tgt = typeof l.target === "string" ? l.target : (l.target as GraphNode).id;
    if (src === node.id) connectedIds.add(tgt);
    if (tgt === node.id) connectedIds.add(src);
  }

  // Pull rule stats if available
  const passed = typeof node.meta.passedRules === "number" ? node.meta.passedRules : null;
  const failed = typeof node.meta.failedRules === "number" ? node.meta.failedRules : null;
  const total  = typeof node.meta.totalRules  === "number" ? node.meta.totalRules  : null;

  return (
    <aside className="w-72 flex-shrink-0 border-l border-white/10 bg-[#0d1117] overflow-y-auto flex flex-col text-white">

      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-white/10 sticky top-0 bg-[#0d1117] z-10">
        <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: color }} />
        <span className="text-xs font-semibold flex-1 truncate">
          {node.type.replace(/_/g, " ")}
        </span>
        <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
          <X size={13} />
        </button>
      </div>

      <div className="p-3 flex-1 space-y-4">

        {/* Label */}
        <div>
          <p className="text-sm font-semibold text-slate-200 leading-snug break-words">{node.label}</p>
        </div>

        {/* Status */}
        <StatusBadge status={node.status} fileType={node.meta?.fileType ? String(node.meta.fileType) : undefined} />

        {/* Rule bar (FILE & DECISION nodes only) */}
        {passed !== null && failed !== null && total !== null && (
          <RuleBar passed={passed} failed={failed} total={total} />
        )}

        {/* Meta fields — grouped */}
        <div className="space-y-2">
          {Object.entries(node.meta)
            .filter(([, v]) => v != null && v !== "")
            .map(([k, v]) => (
              <div key={k} className="flex flex-col gap-0.5">
                <span className="text-[10px] uppercase tracking-wide text-slate-600">
                  {prettyKey(k)}
                </span>
                <span className="text-[11px] text-slate-300 break-all leading-relaxed">
                  {fmtVal(k, v)}
                </span>
              </div>
            ))}
        </div>

        {/* Connected count */}
        <div className="pt-3 border-t border-white/8 text-[11px] text-slate-600">
          {connectedIds.size} directly connected node{connectedIds.size !== 1 ? "s" : ""}
        </div>

        {/* Action buttons */}
        <div className="space-y-1.5">
          {node.type === "BATCH" && (
            <button
              onClick={() => {
                const id = Number(node.id.replace("batch_", ""));
                onViewMode("BY_BATCH");
                onDrillBatch(id);
              }}
              className="flex w-full items-center justify-center gap-1.5 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-xs font-medium transition-colors"
            >
              <ExternalLink size={11} />
              View batch files
            </button>
          )}
          {node.type === "FILE" && (
            <button
              onClick={() => {
                onViewMode("BY_FILE");
                onDrillFile(node.id);
              }}
              className="flex w-full items-center justify-center gap-1.5 py-1.5 rounded-md bg-green-700 hover:bg-green-600 active:bg-green-800 text-xs font-medium transition-colors"
            >
              <ExternalLink size={11} />
              Full file journey
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}

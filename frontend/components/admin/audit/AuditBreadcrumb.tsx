"use client";
import { ChevronRight } from "lucide-react";
import type { ViewMode, GraphNode } from "./types";

interface Props {
  viewMode: ViewMode;
  selectedNode: GraphNode | null;
  nodeCount: number;
  edgeCount: number;
  onBack: () => void;
}

const VIEW_LABELS: Record<ViewMode, string> = {
  ALL:      "All batches",
  BY_BATCH: "Batch view",
  BY_FILE:  "File journey",
  LIST:     "List view",
};

export default function AuditBreadcrumb({
  viewMode, selectedNode, nodeCount, edgeCount, onBack,
}: Props) {
  return (
    <div className="flex h-9 flex-shrink-0 items-center gap-1.5 border-b border-white/10 bg-[#0d1117] px-4 text-xs text-slate-500">
      <button
        onClick={onBack}
        className="hover:text-slate-200 transition-colors shrink-0"
      >
        All batches
      </button>

      {viewMode !== "ALL" && (
        <>
          <ChevronRight size={10} className="flex-shrink-0 text-slate-700" />
          <span className="text-slate-400 shrink-0">{VIEW_LABELS[viewMode]}</span>
        </>
      )}

      {selectedNode && (
        <>
          <ChevronRight size={10} className="flex-shrink-0 text-slate-700" />
          <span className="text-slate-300 truncate max-w-[180px]" title={selectedNode.label}>
            {selectedNode.label}
          </span>
        </>
      )}

      <div className="ml-auto flex items-center gap-2 text-[10px] shrink-0">
        <span className="text-slate-600 tabular-nums">{nodeCount.toLocaleString()} nodes</span>
        <span className="text-slate-700">·</span>
        <span className="text-slate-600 tabular-nums">{edgeCount.toLocaleString()} edges</span>
      </div>
    </div>
  );
}

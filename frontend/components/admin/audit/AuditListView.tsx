"use client";
import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, FileText, GitBranch } from "lucide-react";
import type { GraphNode, ViewMode } from "./types";
import { NODE_COLOR, isSupportingPending } from "./types";
import { displayName } from "@/lib/displayName";

interface Props {
  nodes: GraphNode[];
  onSelectNode: (n: GraphNode) => void;
  onDrillBatch: (id: number) => void;
  onDrillFile:  (id: string)  => void;
  onViewMode:   (m: ViewMode) => void;
  search: string;
}

type SortKey = "label" | "type" | "status";
type SortDir = "asc" | "desc";

function StatusBadge({ status, fileType }: { status: string; fileType?: string }) {
  // A supporting document (contract / engagement letter) is read for cross-document
  // checks but never QC'd on its own, so its file status stays PENDING forever.
  // Showing "Pending" implies it's stuck — label it "Supporting" instead.
  if (isSupportingPending(status, fileType)) {
    return (
      <span
        className="text-[10px] font-medium text-slate-500"
        title="Supporting document — read for cross-document checks, not separately QC'd"
      >
        Supporting
      </span>
    );
  }
  const map: Record<string, string> = {
    PASS:           "text-green-400",
    FAIL:           "text-red-400",
    COMPLETED:      "text-green-400",
    REVIEW_PENDING: "text-amber-400",
    IN_REVIEW:      "text-indigo-400",
    QC_PROCESSING:  "text-blue-400",
    ERROR:          "text-red-400",
    DONE:           "text-cyan-400",
  };
  return (
    <span className={`text-[10px] font-medium ${map[status] ?? "text-slate-400"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

export default function AuditListView({
  nodes, onSelectNode, onDrillBatch, onDrillFile, onViewMode, search,
}: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("type");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [typeFilter, setTypeFilter] = useState("");

  const sorted = useMemo(() => {
    let list = nodes.filter(n => {
      if (typeFilter && n.type !== typeFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          n.label.toLowerCase().includes(q) ||
          n.type.toLowerCase().includes(q) ||
          n.status.toLowerCase().includes(q) ||
          Object.values(n.meta).some(v => String(v ?? "").toLowerCase().includes(q))
        );
      }
      return true;
    });

    list = [...list].sort((a, b) => {
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      return sortDir === "asc"
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });

    return list;
  }, [nodes, search, sortKey, sortDir, typeFilter]);

  const types = useMemo(() => [...new Set(nodes.map(n => n.type))].sort(), [nodes]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("asc"); }
  }

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <ChevronDown size={9} className="text-slate-700" />;
    return sortDir === "asc"
      ? <ChevronUp size={9} className="text-indigo-400" />
      : <ChevronDown size={9} className="text-indigo-400" />;
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[#080C10]">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-white/8 bg-[#0d1117]">
        <span className="text-[11px] text-slate-500 tabular-nums">
          {sorted.length.toLocaleString()} / {nodes.length.toLocaleString()} nodes
        </span>
        <div className="flex items-center gap-1.5 ml-auto">
          <span className="text-[10px] text-slate-600">Type</span>
          <select
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value)}
            className="bg-[#161b22] border border-white/10 rounded px-1.5 py-0.5 text-[10px] text-slate-300 outline-none"
          >
            <option value="">All</option>
            {types.map(t => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[#0d1117] z-10">
            <tr className="text-[10px] text-slate-600 uppercase tracking-wider">
              <th className="text-left px-4 py-2 w-8">&nbsp;</th>
              <th
                className="text-left px-2 py-2 cursor-pointer hover:text-slate-300 select-none"
                onClick={() => toggleSort("label")}
              >
                <span className="flex items-center gap-1">Label <SortIcon col="label" /></span>
              </th>
              <th
                className="text-left px-2 py-2 cursor-pointer hover:text-slate-300 select-none w-28"
                onClick={() => toggleSort("type")}
              >
                <span className="flex items-center gap-1">Type <SortIcon col="type" /></span>
              </th>
              <th
                className="text-left px-2 py-2 cursor-pointer hover:text-slate-300 select-none w-32"
                onClick={() => toggleSort("status")}
              >
                <span className="flex items-center gap-1">Status <SortIcon col="status" /></span>
              </th>
              <th className="text-left px-2 py-2 w-24">Reviewer</th>
              <th className="text-left px-2 py-2 w-16">Rules</th>
              <th className="w-20 px-2 py-2">&nbsp;</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(node => {
              const color = NODE_COLOR[node.type as keyof typeof NODE_COLOR] ?? "#64748b";
              const passed = typeof node.meta.passedRules === "number" ? node.meta.passedRules : null;
              const total  = typeof node.meta.totalRules  === "number" ? node.meta.totalRules  : null;
              const pct = (passed !== null && total) ? Math.round((passed / total) * 100) : null;
              return (
                <tr
                  key={node.id}
                  onClick={() => onSelectNode(node)}
                  className="border-b border-white/4 hover:bg-white/3 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-2">
                    <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: color }} />
                  </td>
                  <td className="px-2 py-2">
                    <span className="text-slate-200 font-medium truncate block max-w-[220px]" title={node.label}>
                      {node.label}
                    </span>
                    {node.meta.client && (
                      <span className="text-[10px] text-slate-600">{String(node.meta.client)}</span>
                    )}
                  </td>
                  <td className="px-2 py-2 text-[10px] text-slate-400">
                    {node.type.replace(/_/g, " ")}
                  </td>
                  <td className="px-2 py-2">
                    <StatusBadge status={node.status} fileType={node.meta.fileType ? String(node.meta.fileType) : undefined} />
                  </td>
                  <td className="px-2 py-2 text-[10px] text-slate-500 truncate max-w-[80px]"
                      title={String(node.meta.reviewer ?? node.meta.reviewerEmail ?? "")}>
                    {node.meta.reviewer || node.meta.reviewerEmail
                      ? displayName(String(node.meta.reviewer ?? node.meta.reviewerEmail))
                      : "—"}
                  </td>
                  <td className="px-2 py-2">
                    {pct !== null ? (
                      <div className="flex items-center gap-1.5">
                        <div className="w-12 h-1 rounded-full bg-white/5 overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${pct}%`,
                              background: pct > 70 ? "#22c55e" : pct > 40 ? "#f59e0b" : "#ef4444",
                            }}
                          />
                        </div>
                        <span className="text-[10px] text-slate-500">{pct}%</span>
                      </div>
                    ) : "—"}
                  </td>
                  <td className="px-2 py-2 text-right">
                    {node.type === "BATCH" && (
                      <button
                        onClick={e => { e.stopPropagation(); onViewMode("BY_BATCH"); onDrillBatch(Number(node.id.replace("batch_", ""))); }}
                        className="text-[10px] text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-0.5 ml-auto"
                      >
                        <GitBranch size={9} /> Files
                      </button>
                    )}
                    {node.type === "FILE" && (
                      <button
                        onClick={e => { e.stopPropagation(); onViewMode("BY_FILE"); onDrillFile(node.id); }}
                        className="text-[10px] text-green-400 hover:text-green-300 transition-colors flex items-center gap-0.5 ml-auto"
                      >
                        <FileText size={9} /> Journey
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {sorted.length === 0 && (
          <div className="flex items-center justify-center h-32 text-sm text-slate-600">
            No nodes match the current filter
          </div>
        )}
      </div>
    </div>
  );
}

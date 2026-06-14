"use client";
import { useRef } from "react";
import {
  Network, RefreshCw, Search, X, ChevronRight, GitBranch,
  Clock, FileText, AlertCircle, CheckCircle2, Filter, List,
} from "lucide-react";
import type { ViewMode, NodeType, BatchSummary, GraphData } from "./types";
import { NODE_COLOR } from "./types";

interface Props {
  search: string;
  onSearchChange: (v: string) => void;
  onSearch: () => void;
  onClear: () => void;
  viewMode: ViewMode;
  onViewMode: (m: ViewMode) => void;
  onBack: () => void;
  filterStatus: string;
  onFilterStatus: (v: string) => void;
  filtersOpen: boolean;
  onToggleFilters: () => void;
  batches: BatchSummary[];
  onSelectBatch: (id: number) => void;
  graphData: GraphData;
  loading: boolean;
  onRefresh: () => void;
  showCharts: boolean;
  onToggleCharts: () => void;
}

function StatRow({ icon: Icon, label, value, color }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string; value: number; color: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <Icon size={11} className={color} />
      <span className="text-xs text-slate-300 tabular-nums font-semibold">{value.toLocaleString()}</span>
      <span className="text-[10px] text-slate-600">{label}</span>
    </div>
  );
}

export default function AuditSidebar({
  search, onSearchChange, onSearch, onClear,
  viewMode, onViewMode, onBack,
  filterStatus, onFilterStatus, filtersOpen, onToggleFilters,
  batches, onSelectBatch,
  graphData, loading, onRefresh,
  showCharts, onToggleCharts,
}: Props) {
  const searchRef = useRef<HTMLInputElement>(null);

  const stats = {
    batches:   graphData.nodes.filter(n => n.type === "BATCH").length,
    files:     graphData.nodes.filter(n => n.type === "FILE").length,
    sessions:  graphData.nodes.filter(n => n.type === "REVIEW_SESSION").length,
    decisions: graphData.nodes.filter(n => n.type === "DECISION").length,
    submits:   graphData.nodes.filter(n => n.type === "SUBMIT").length,
  };

  return (
    <aside className="w-64 flex-shrink-0 flex flex-col border-r border-white/10 bg-[#0d1117] overflow-y-auto">

      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-white/10">
        <Network size={13} className="text-indigo-400 flex-shrink-0" />
        <span className="text-xs font-semibold flex-1">Audit Graph</span>
        <button
          onClick={onToggleCharts}
          title={showCharts ? "Hide analytics" : "Show analytics"}
          className={`text-[10px] px-1.5 py-0.5 rounded border transition-colors ${
            showCharts
              ? "border-indigo-500/50 text-indigo-400 bg-indigo-950/40"
              : "border-white/10 text-slate-500 hover:text-slate-300"
          }`}
        >
          Analytics
        </button>
      </div>

      {/* Search */}
      <div className="p-3 border-b border-white/10">
        <div className="relative">
          <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
          <input
            ref={searchRef}
            value={search}
            onChange={e => onSearchChange(e.target.value)}
            onKeyDown={e => e.key === "Enter" && onSearch()}
            placeholder="Batch ID, subject address, file, reviewer, client…"
            className="w-full bg-[#161b22] border border-white/10 rounded-md pl-8 pr-7 py-1.5 text-xs text-slate-300 placeholder-slate-600 outline-none focus:border-indigo-500/60 transition-colors"
          />
          {search && (
            <button onClick={onClear} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white transition-colors">
              <X size={11} />
            </button>
          )}
        </div>
        <button
          onClick={onSearch}
          className="mt-2 w-full py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-xs font-medium transition-colors"
        >
          Search
        </button>
      </div>

      {/* View mode */}
      <div className="p-3 border-b border-white/10">
        <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-2">View</p>
        <div className="grid grid-cols-3 gap-1">
          {([
            { mode: "ALL"      as ViewMode, label: "Graph",    Icon: Network   },
            { mode: "BY_BATCH" as ViewMode, label: "Batch",    Icon: GitBranch },
            { mode: "LIST"     as ViewMode, label: "List",     Icon: List      },
          ]).map(({ mode, label, Icon }) => (
            <button
              key={mode}
              onClick={() => onViewMode(mode)}
              className={`flex flex-col items-center gap-0.5 py-1.5 rounded-md text-[10px] font-medium transition-colors ${
                viewMode === mode
                  ? "bg-indigo-600 text-white"
                  : "bg-[#161b22] text-slate-400 hover:text-white border border-white/8"
              }`}
            >
              <Icon size={11} />
              {label}
            </button>
          ))}
        </div>
        {viewMode !== "ALL" && (
          <button
            onClick={onBack}
            className="mt-2 flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            ← All batches
          </button>
        )}
      </div>

      {/* Batch picker */}
      {viewMode === "BY_BATCH" && batches.length > 0 && (
        <div className="p-3 border-b border-white/10">
          <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-2">Select batch</p>
          <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
            {batches.map(b => (
              <button
                key={b.id}
                onClick={() => onSelectBatch(b.id)}
                className="w-full text-left px-2 py-1.5 rounded text-[11px] bg-[#161b22] hover:bg-white/5 text-slate-300 border border-white/5 flex items-center gap-1.5 overflow-hidden"
              >
                <GitBranch size={9} className="text-indigo-400 flex-shrink-0" />
                <span className="font-medium truncate">{b.parentBatchId}</span>
                {b.client?.name && (
                  <span className="text-slate-500 truncate text-[10px] ml-auto">{b.client.name}</span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="p-3 border-b border-white/10">
        <button
          onClick={onToggleFilters}
          className="flex items-center gap-2 w-full text-[10px] uppercase tracking-widest text-slate-600 hover:text-slate-400 transition-colors"
        >
          <Filter size={10} />
          Filters
          <ChevronRight size={10} className={`ml-auto transition-transform ${filtersOpen ? "rotate-90" : ""}`} />
        </button>
        {filtersOpen && (
          <div className="mt-2 space-y-2">
            <div>
              <label className="text-[10px] text-slate-500 block mb-1">Status</label>
              <select
                value={filterStatus}
                onChange={e => onFilterStatus(e.target.value)}
                className="w-full bg-[#161b22] border border-white/10 rounded px-2 py-1.5 text-xs text-slate-300 outline-none focus:border-indigo-500/50"
              >
                <option value="">All statuses</option>
                {["UPLOADED","QC_PROCESSING","REVIEW_PENDING","IN_REVIEW","COMPLETED","ERROR"].map(s => (
                  <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                ))}
              </select>
            </div>
            <div className="flex gap-1">
              <button
                onClick={onSearch}
                className="flex-1 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-xs transition-colors"
              >
                Apply
              </button>
              <button
                onClick={onClear}
                className="py-1 px-2 rounded bg-[#161b22] border border-white/10 text-xs text-slate-400 hover:text-white transition-colors"
              >
                Reset
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="p-3 border-b border-white/10">
        <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-2">Legend</p>
        <div className="space-y-1.5">
          {(Object.entries(NODE_COLOR) as [NodeType, string][]).map(([type, color]) => (
            <div key={type} className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color }} />
              <span className="text-[11px] text-slate-400">{type.replace(/_/g, " ")}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Stats */}
      <div className="p-3 mt-auto">
        <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-2">Current view</p>
        <div className="space-y-1.5">
          <StatRow icon={GitBranch}    label="Batches"   value={stats.batches}   color="text-indigo-400" />
          <StatRow icon={FileText}     label="Files"     value={stats.files}     color="text-green-400" />
          <StatRow icon={Clock}        label="Sessions"  value={stats.sessions}  color="text-amber-400" />
          <StatRow icon={CheckCircle2} label="Decisions" value={stats.decisions} color="text-orange-400" />
          <StatRow icon={AlertCircle}  label="Submits"   value={stats.submits}   color="text-cyan-400" />
        </div>
        <button
          onClick={onRefresh}
          className="mt-3 flex w-full items-center justify-center gap-1.5 py-1.5 rounded-md border border-white/10 text-xs text-slate-400 hover:text-white hover:border-white/20 transition-colors"
        >
          <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>
    </aside>
  );
}

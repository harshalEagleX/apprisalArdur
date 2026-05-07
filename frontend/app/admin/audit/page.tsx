"use client";
import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import {
  Network, RefreshCw, Maximize2, Search, X, ChevronRight,
  GitBranch, Clock, FileText, AlertCircle, CheckCircle2, Filter,
} from "lucide-react";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

// ── Types ─────────────────────────────────────────────────────────────────────
type NodeType = "BATCH" | "FILE" | "REVIEW_SESSION" | "DECISION" | "RE_REVIEW" | "SUBMIT";
type ViewMode = "ALL" | "BY_BATCH" | "BY_FILE" | "BY_REVIEWER";

interface GraphNode {
  id: string;
  label: string;
  type: NodeType;
  status: string;
  meta: Record<string, string | number | null | undefined>;
  x?: number;
  y?: number;
  z?: number;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  type: string;
  timestamp?: string;
}

interface GraphData { nodes: GraphNode[]; links: GraphLink[] }

interface BatchSummary {
  id: number;
  parentBatchId: string;
  status: string;
  client?: { name: string; code: string };
  fileCount: number;
  assignedReviewer?: { id: number; username: string };
}

// ── Visual config ─────────────────────────────────────────────────────────────
const NODE_COLOR: Record<NodeType, string> = {
  BATCH:          "#6366f1",
  FILE:           "#22c55e",
  REVIEW_SESSION: "#f59e0b",
  DECISION:       "#f97316",
  RE_REVIEW:      "#ef4444",
  SUBMIT:         "#06b6d4",
};

const NODE_SIZE: Record<NodeType, number> = {
  BATCH:          14,
  FILE:           9,
  REVIEW_SESSION: 7,
  DECISION:       7,
  RE_REVIEW:      9,
  SUBMIT:         7,
};

const EDGE_COLOR: Record<string, string> = {
  CONTAINS:    "#ffffff22",
  HAS_SESSION: "#f59e0b44",
  RESULTED_IN: "#f9743644",
  LED_TO:      "#06b6d444",
  RE_REVIEW:   "#ef444466",
  ASSIGNS:     "#a78bfa33",
};

const ForceGraph2D = dynamic(
  () => import("@/components/admin/AuditForceGraph"),
  { ssr: false, loading: () => <GraphSkeleton /> }
);

// ── API helpers ───────────────────────────────────────────────────────────────
async function fetchGraph(url: string): Promise<GraphData> {
  const r = await fetch(url, { credentials: "include" });
  if (!r.ok) throw new Error(`Graph API error: ${r.status}`);
  return r.json() as Promise<GraphData>;
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function AdminAuditPage() {
  const [graphData, setGraphData]   = useState<GraphData>({ nodes: [], links: [] });
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState("");
  const [viewMode, setViewMode]     = useState<ViewMode>("ALL");
  const [search, setSearch]         = useState("");
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlighted, setHighlighted]   = useState<Set<string>>(new Set());
  const [graphSize, setGraphSize]       = useState({ w: 800, h: 600 });
  const [filterStatus, setFilterStatus] = useState("");
  const [filtersOpen, setFiltersOpen]   = useState(false);
  const [batches, setBatches]           = useState<BatchSummary[]>([]);
  const graphRef      = useRef<{ zoomToFit: (ms?: number) => void } | null>(null);
  const containerRef  = useRef<HTMLDivElement | null>(null);
  const searchRef     = useRef<HTMLInputElement>(null);

  // Load overview batches list for the batch picker
  const loadBatchList = useCallback(async () => {
    try {
      const r = await fetch(`${JAVA}/api/admin/batches?page=0&size=100`, { credentials: "include" });
      if (r.ok) {
        const d = await r.json() as { content: BatchSummary[] };
        setBatches(d.content ?? []);
      }
    } catch { /* silent */ }
  }, []);

  const loadGraph = useCallback(async (q?: string, status?: string) => {
    setLoading(true); setError("");
    try {
      let url = `${JAVA}/api/graph/overview`;
      if (q || status) {
        const p = new URLSearchParams();
        if (q) p.set("q", q);
        if (status) p.set("status", status);
        url = `${JAVA}/api/graph/search?${p.toString()}`;
      }
      console.log("[audit-graph] loadGraph →", url);
      const data = await fetchGraph(url);
      console.log("[audit-graph] overview response:", {
        nodes: data.nodes.length,
        links: data.links.length,
        nodeTypes: [...new Set(data.nodes.map(n => n.type))],
        sample: data.nodes.slice(0, 3),
      });
      setGraphData(data);
      setSelectedNode(null);
      setHighlighted(new Set());
    } catch (e) {
      console.error("[audit-graph] loadGraph error:", e);
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadBatchSubgraph = useCallback(async (batchId: number) => {
    setLoading(true); setError("");
    try {
      const url = `${JAVA}/api/graph/batch/${batchId}`;
      console.log("[audit-graph] loadBatchSubgraph →", url);
      const data = await fetchGraph(url);
      console.log("[audit-graph] batch subgraph:", {
        nodes: data.nodes.length,
        links: data.links.length,
        nodeTypes: [...new Set(data.nodes.map(n => n.type))],
      });
      setGraphData(data);
      setSelectedNode(null); setHighlighted(new Set());
    } catch (e) {
      console.error("[audit-graph] loadBatchSubgraph error:", e);
      setError(String(e));
    } finally { setLoading(false); }
  }, []);

  const loadFileSubgraph = useCallback(async (fileId: string) => {
    const id = fileId.replace("file_", "");
    setLoading(true); setError("");
    try {
      const url = `${JAVA}/api/graph/file/${id}`;
      console.log("[audit-graph] loadFileSubgraph →", url);
      const data = await fetchGraph(url);
      console.log("[audit-graph] file subgraph:", {
        nodes: data.nodes.length,
        links: data.links.length,
        nodeTypes: [...new Set(data.nodes.map(n => n.type))],
        nodes_detail: data.nodes,
      });
      setGraphData(data);
      setSelectedNode(null); setHighlighted(new Set());
    } catch (e) {
      console.error("[audit-graph] loadFileSubgraph error:", e);
      setError(String(e));
    } finally { setLoading(false); }
  }, []);

  // Initial load
  useEffect(() => {
    void loadBatchList();
    void loadGraph();
  }, [loadGraph, loadBatchList]);

  // Resize observer
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) setGraphSize({ w: Math.floor(width), h: Math.floor(height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const handleSearch = useCallback(() => {
    void loadGraph(search.trim() || undefined, filterStatus || undefined);
  }, [loadGraph, search, filterStatus]);

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node);
    const connected = new Set<string>([node.id]);
    for (const l of graphData.links) {
      const src = typeof l.source === "string" ? l.source : (l.source as GraphNode).id;
      const tgt = typeof l.target === "string" ? l.target : (l.target as GraphNode).id;
      if (src === node.id) connected.add(tgt);
      if (tgt === node.id) connected.add(src);
    }
    setHighlighted(connected);

    // Drill-down on double-click for batch→file or file→journey
    if (node.type === "BATCH") {
      setViewMode("BY_BATCH");
      const batchId = Number(node.id.replace("batch_", ""));
      void loadBatchSubgraph(batchId);
    } else if (node.type === "FILE") {
      setViewMode("BY_FILE");
      void loadFileSubgraph(node.id);
    }
  }, [graphData.links, loadBatchSubgraph, loadFileSubgraph]);

  const handleBack = useCallback(() => {
    setViewMode("ALL");
    setSelectedNode(null);
    setHighlighted(new Set());
    void loadGraph(search.trim() || undefined, filterStatus || undefined);
  }, [loadGraph, search, filterStatus]);

  const stats = useMemo(() => ({
    batches:  graphData.nodes.filter(n => n.type === "BATCH").length,
    files:    graphData.nodes.filter(n => n.type === "FILE").length,
    sessions: graphData.nodes.filter(n => n.type === "REVIEW_SESSION").length,
    decisions:graphData.nodes.filter(n => n.type === "DECISION").length,
    submits:  graphData.nodes.filter(n => n.type === "SUBMIT").length,
  }), [graphData.nodes]);

  return (
    <div className="flex h-screen bg-slate-950 text-white overflow-hidden">

      {/* ── Left control panel ───────────────────────────────────────── */}
      <aside className="w-72 flex-shrink-0 flex flex-col border-r border-white/10 bg-[#0d1117] overflow-y-auto">

        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-white/10">
          <Network size={14} className="text-indigo-400" />
          <span className="text-sm font-semibold">Audit Graph</span>
        </div>

        {/* Search */}
        <div className="p-3 border-b border-white/10">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              ref={searchRef}
              value={search}
              onChange={e => setSearch(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
              placeholder="Search batches, files, reviewers…"
              className="w-full bg-[#161b22] border border-white/10 rounded-md pl-8 pr-8 py-1.5 text-xs text-slate-300 placeholder-slate-600 outline-none focus:border-indigo-500/50"
            />
            {search && (
              <button onClick={() => { setSearch(""); void loadGraph(); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white">
                <X size={11} />
              </button>
            )}
          </div>
          <button onClick={handleSearch}
            className="mt-2 w-full py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 text-xs font-medium transition-colors">
            Search
          </button>
        </div>

        {/* View mode */}
        <div className="p-3 border-b border-white/10">
          <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-2">View mode</p>
          <div className="grid grid-cols-2 gap-1">
            {(["ALL", "BY_BATCH"] as ViewMode[]).map(m => (
              <button key={m}
                onClick={() => {
                  setViewMode(m);
                  if (m === "ALL") void loadGraph(search.trim() || undefined, filterStatus || undefined);
                }}
                className={`py-1.5 rounded-md text-[11px] font-medium transition-colors ${viewMode === m ? "bg-indigo-600 text-white" : "bg-[#161b22] text-slate-400 hover:text-white border border-white/10"}`}>
                {m === "ALL" ? "All" : "By Batch"}
              </button>
            ))}
            {(["BY_FILE", "BY_REVIEWER"] as ViewMode[]).map(m => (
              <button key={m}
                onClick={() => setViewMode(m)}
                className={`py-1.5 rounded-md text-[11px] font-medium transition-colors ${viewMode === m ? "bg-indigo-600 text-white" : "bg-[#161b22] text-slate-400 hover:text-white border border-white/10"}`}>
                {m === "BY_FILE" ? "By File" : "By Reviewer"}
              </button>
            ))}
          </div>
          {viewMode !== "ALL" && (
            <button onClick={handleBack}
              className="mt-2 flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300">
              ← Back to all batches
            </button>
          )}
        </div>

        {/* Batch picker (BY_BATCH mode) */}
        {viewMode === "BY_BATCH" && batches.length > 0 && (
          <div className="p-3 border-b border-white/10">
            <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-2">Select batch</p>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {batches.map(b => (
                <button key={b.id}
                  onClick={() => void loadBatchSubgraph(b.id)}
                  className="w-full text-left px-2 py-1.5 rounded text-[11px] bg-[#161b22] hover:bg-white/5 text-slate-300 border border-white/5 truncate">
                  <span className="font-medium">{b.parentBatchId}</span>
                  <span className="ml-1 text-slate-500">{b.client?.name}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="p-3 border-b border-white/10">
          <button onClick={() => setFiltersOpen(o => !o)}
            className="flex items-center gap-2 w-full text-[10px] uppercase tracking-widest text-slate-600 hover:text-slate-400">
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
                  onChange={e => setFilterStatus(e.target.value)}
                  className="w-full bg-[#161b22] border border-white/10 rounded px-2 py-1.5 text-xs text-slate-300 outline-none">
                  <option value="">All statuses</option>
                  {["UPLOADED","QC_PROCESSING","REVIEW_PENDING","IN_REVIEW","COMPLETED","ERROR"].map(s => (
                    <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                  ))}
                </select>
              </div>
              <div className="flex gap-1">
                <button onClick={handleSearch}
                  className="flex-1 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-xs transition-colors">
                  Apply
                </button>
                <button onClick={() => { setFilterStatus(""); setSearch(""); void loadGraph(); }}
                  className="py-1 px-2 rounded bg-[#161b22] border border-white/10 text-xs text-slate-400 hover:text-white">
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
                <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: color }} />
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
          <button onClick={() => void loadGraph()}
            className="mt-3 flex w-full items-center justify-center gap-1.5 py-1.5 rounded-md border border-white/10 text-xs text-slate-400 hover:text-white transition-colors">
            <RefreshCw size={11} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </aside>

      {/* ── Graph canvas ─────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Breadcrumb bar */}
        <div className="flex h-9 flex-shrink-0 items-center gap-2 border-b border-white/10 bg-[#0d1117] px-4 text-xs text-slate-500">
          <button onClick={handleBack} className="hover:text-white transition-colors">All batches</button>
          {viewMode !== "ALL" && (
            <>
              <ChevronRight size={10} />
              <span className="text-slate-300">{viewMode === "BY_BATCH" ? "Batch view" : viewMode === "BY_FILE" ? "File journey" : "Reviewer view"}</span>
            </>
          )}
          {selectedNode && (
            <>
              <ChevronRight size={10} />
              <span className="text-slate-400 truncate max-w-xs">{selectedNode.label}</span>
            </>
          )}
          <div className="ml-auto flex items-center gap-2 text-[10px]">
            <span className="text-slate-600">{graphData.nodes.length} nodes</span>
            <span className="text-slate-700">·</span>
            <span className="text-slate-600">{graphData.links.length} edges</span>
          </div>
        </div>

        <div className="flex flex-1 overflow-hidden relative">
          {/* Graph */}
          <div ref={containerRef} className="flex-1 relative bg-[#080C10]">
            {error && <ErrorOverlay message={error} />}
            {loading && !error && <GraphSkeleton />}
            {!loading && !error && graphData.nodes.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-600">
                No data — try refreshing or checking the API server.
              </div>
            )}
            {!loading && !error && graphData.nodes.length > 0 && (
              <ForceGraph2D
                ref={graphRef as never}
                graphData={graphData as never}
                width={graphSize.w}
                height={graphSize.h}
                backgroundColor="#080C10"
                onEngineStop={() => { graphRef.current?.zoomToFit?.(400); }}
                nodeLabel={(n: unknown) => {
                  const node = n as GraphNode;
                  const lines = [
                    `${node.type.replace(/_/g, " ")}: ${node.label}`,
                    `Status: ${node.status}`,
                  ];
                  if (node.meta?.reviewer) lines.push(`Reviewer: ${String(node.meta.reviewer)}`);
                  if (node.meta?.client)   lines.push(`Client: ${String(node.meta.client)}`);
                  if (node.meta?.fileCount !== undefined) lines.push(`Files: ${String(node.meta.fileCount)}`);
                  return lines.join("\n");
                }}
                nodeColor={(n: unknown) => {
                  const node = n as GraphNode;
                  const dim = highlighted.size > 0 && !highlighted.has(node.id);
                  const base = NODE_COLOR[node.type as NodeType] ?? "#64748b";
                  return dim ? base + "28" : base;
                }}
                nodeVal={(n: unknown) => NODE_SIZE[(n as GraphNode).type as NodeType] ?? 6}
                nodeCanvasObject={(n: unknown, ctx: CanvasRenderingContext2D, globalScale: number) => {
                  const node = n as GraphNode & { x?: number; y?: number };
                  if (node.x == null || node.y == null) return;
                  const size  = NODE_SIZE[node.type as NodeType] ?? 6;
                  const color = NODE_COLOR[node.type as NodeType] ?? "#64748b";
                  const dim   = highlighted.size > 0 && !highlighted.has(node.id);
                  ctx.globalAlpha = dim ? 0.15 : 1;
                  ctx.beginPath();
                  ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
                  ctx.fillStyle = color;
                  ctx.fill();
                  if (highlighted.has(node.id) || node.id === selectedNode?.id) {
                    ctx.strokeStyle = "#ffffff66";
                    ctx.lineWidth = 1.5 / globalScale;
                    ctx.stroke();
                  }
                  ctx.globalAlpha = 1;
                }}
                linkColor={(l: unknown) => {
                  const link = l as GraphLink;
                  return EDGE_COLOR[link.type] ?? "#ffffff14";
                }}
                linkWidth={1}
                linkDirectionalArrowLength={4}
                linkDirectionalArrowRelPos={1}
                onNodeClick={handleNodeClick as never}
                onBackgroundClick={() => { setSelectedNode(null); setHighlighted(new Set()); }}
                cooldownTicks={100}
              />
            )}

            {/* Zoom button */}
            <button
              onClick={() => graphRef.current?.zoomToFit?.(400)}
              className="absolute bottom-4 right-4 flex h-8 w-8 items-center justify-center rounded-md border border-white/10 bg-[#11161C] text-slate-400 hover:text-white">
              <Maximize2 size={13} />
            </button>

            {/* Click hint */}
            {graphData.nodes.length > 0 && !selectedNode && !loading && (
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-[11px] text-slate-700 pointer-events-none">
                Click any node to inspect · Double-click a batch or file to drill in
              </div>
            )}
          </div>

          {/* ── Detail drawer ──────────────────────────────────────────── */}
          {selectedNode && (
            <aside className="w-72 flex-shrink-0 border-l border-white/10 bg-[#0d1117] overflow-y-auto flex flex-col">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-white/10">
                <span className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{ background: NODE_COLOR[selectedNode.type as NodeType] ?? "#64748b" }} />
                <span className="text-xs font-semibold text-white flex-1 truncate">
                  {selectedNode.type.replace(/_/g, " ")}
                </span>
                <button onClick={() => { setSelectedNode(null); setHighlighted(new Set()); }}
                  className="text-slate-500 hover:text-white">
                  <X size={13} />
                </button>
              </div>

              <div className="p-4 flex-1">
                <p className="text-sm font-medium text-slate-200 leading-snug mb-4 break-words">
                  {selectedNode.label}
                </p>

                {/* Status badge */}
                <div className="mb-4">
                  <StatusBadge status={selectedNode.status} />
                </div>

                {/* Meta fields */}
                <div className="space-y-2">
                  {Object.entries(selectedNode.meta)
                    .filter(([, v]) => v != null && v !== "")
                    .map(([k, v]) => (
                      <div key={k} className="flex flex-col gap-0.5">
                        <span className="text-[10px] uppercase tracking-wide text-slate-600">
                          {k.replace(/([A-Z])/g, " $1").trim()}
                        </span>
                        <span className="text-[12px] text-slate-300 break-words">
                          {formatMetaValue(k, v)}
                        </span>
                      </div>
                    ))}
                </div>

                {/* Connected count */}
                <div className="mt-6 pt-4 border-t border-white/10 text-[11px] text-slate-600">
                  {highlighted.size - 1} directly connected node{highlighted.size !== 2 ? "s" : ""}
                </div>

                {/* Drill-in button */}
                {selectedNode.type === "BATCH" && (
                  <button
                    onClick={() => {
                      const id = Number(selectedNode.id.replace("batch_", ""));
                      setViewMode("BY_BATCH");
                      void loadBatchSubgraph(id);
                    }}
                    className="mt-3 w-full py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 text-xs font-medium transition-colors">
                    View batch files
                  </button>
                )}
                {selectedNode.type === "FILE" && (
                  <button
                    onClick={() => {
                      setViewMode("BY_FILE");
                      void loadFileSubgraph(selectedNode.id);
                    }}
                    className="mt-3 w-full py-1.5 rounded-md bg-green-700 hover:bg-green-600 text-xs font-medium transition-colors">
                    View full file journey
                  </button>
                )}
              </div>
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Small helpers ─────────────────────────────────────────────────────────────

function formatMetaValue(key: string, val: string | number | null | undefined): string {
  if (val == null) return "—";
  const s = String(val);
  if ((key.endsWith("At") || key.endsWith("Date")) && s.includes("T")) {
    try { return new Date(s).toLocaleString(); } catch { /* fall through */ }
  }
  return s;
}

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    PASS:           "bg-green-950 text-green-400 border-green-800",
    FAIL:           "bg-red-950 text-red-400 border-red-800",
    DONE:           "bg-cyan-950 text-cyan-400 border-cyan-800",
    COMPLETED:      "bg-green-950 text-green-400 border-green-800",
    REVIEW_PENDING: "bg-amber-950 text-amber-400 border-amber-800",
    QC_PROCESSING:  "bg-blue-950 text-blue-400 border-blue-800",
    UPLOADED:       "bg-slate-800 text-slate-400 border-slate-700",
    ERROR:          "bg-red-950 text-red-400 border-red-800",
  };
  const cls = colorMap[status] ?? "bg-slate-800 text-slate-400 border-slate-700";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] font-medium ${cls}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function StatRow({ icon: Icon, label, value, color }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string; value: number; color: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <Icon size={11} className={color} />
      <span className="text-xs text-slate-300 tabular-nums font-medium">{value}</span>
      <span className="text-[10px] text-slate-600">{label}</span>
    </div>
  );
}

function ErrorOverlay({ message }: { message: string }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center">
      <div className="rounded-lg border border-red-500/25 bg-red-950/40 px-6 py-4 text-sm text-red-200 text-center max-w-sm">
        <AlertCircle size={20} className="mx-auto mb-2" />
        {message}
        <div className="mt-2 text-xs text-slate-400">Check the Java API server is running.</div>
      </div>
    </div>
  );
}

function GraphSkeleton() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-center">
        <div className="relative mx-auto mb-4 h-20 w-20">
          {[0, 1, 2, 3].map(i => (
            <div key={i} className="absolute inset-0 rounded-full border border-indigo-500/30 animate-ping"
              style={{ animationDelay: `${i * 0.25}s`, animationDuration: "2s" }} />
          ))}
          <Network size={28} className="absolute inset-0 m-auto text-indigo-400" />
        </div>
        <div className="text-sm text-slate-400">Building graph…</div>
        <div className="mt-1 text-xs text-slate-600">Fetching nodes and relationships</div>
      </div>
    </div>
  );
}

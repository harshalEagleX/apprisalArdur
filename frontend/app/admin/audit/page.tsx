"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { Network, Maximize2, AlertCircle } from "lucide-react";
import type { GraphData, GraphNode, ViewMode, BatchSummary } from "@/components/admin/audit/types";
import { NODE_COLOR, NODE_SIZE, EDGE_COLOR, nodeStatusLabel } from "@/components/admin/audit/types";
import { displayName } from "@/lib/displayName";
import { JAVA } from "@/lib/config";
import AuditSidebar     from "@/components/admin/audit/AuditSidebar";
import AuditBreadcrumb  from "@/components/admin/audit/AuditBreadcrumb";
import AuditNodeDrawer  from "@/components/admin/audit/AuditNodeDrawer";
import AuditListView    from "@/components/admin/audit/AuditListView";

const AuditChartsPanel = dynamic(
  () => import("@/components/admin/audit/AuditChartsPanel"),
  { ssr: false }
);

const ForceGraph2D = dynamic(
  () => import("@/components/admin/AuditForceGraph"),
  { ssr: false, loading: () => <GraphSkeleton /> }
);

async function fetchGraph(url: string): Promise<GraphData> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30_000);
  try {
    const r = await fetch(url, { credentials: "include", signal: controller.signal });
    if (!r.ok) throw new Error(`Graph API ${r.status}`);
    return r.json() as Promise<GraphData>;
  } finally {
    clearTimeout(timer);
  }
}

export default function AdminAuditPage() {
  // ── Core state ──────────────────────────────────────────────────────────────
  const [graphData,     setGraphData]     = useState<GraphData>({ nodes: [], links: [] });
  const [loading,       setLoading]       = useState(true);
  const [error,         setError]         = useState("");
  const [viewMode,      setViewMode]      = useState<ViewMode>("ALL");
  const [search,        setSearch]        = useState("");
  const [filterStatus,  setFilterStatus]  = useState("");
  const [filtersOpen,   setFiltersOpen]   = useState(false);
  const [selectedNode,  setSelectedNode]  = useState<GraphNode | null>(null);
  const [highlighted,   setHighlighted]   = useState<Set<string>>(new Set());
  const [batches,       setBatches]       = useState<BatchSummary[]>([]);
  const [showCharts,    setShowCharts]    = useState(true);
  const [graphSize,     setGraphSize]     = useState({ w: 800, h: 600 });

  const graphRef     = useRef<{
    zoomToFit: (ms?: number) => void;
    d3Force: (name: string) => { strength?: (s: number) => void; distance?: (d: number) => void } | undefined;
    d3ReheatSimulation: () => void;
  } | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // ── Data loading ────────────────────────────────────────────────────────────
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
        if (q)      p.set("q", q);
        if (status) p.set("status", status);
        url = `${JAVA}/api/graph/search?${p.toString()}`;
      }
      const data = await fetchGraph(url);
      setGraphData(data);
      setSelectedNode(null);
      setHighlighted(new Set());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadBatchSubgraph = useCallback(async (batchId: number) => {
    setLoading(true); setError("");
    try {
      const data = await fetchGraph(`${JAVA}/api/graph/batch/${batchId}`);
      setGraphData(data);
      setSelectedNode(null); setHighlighted(new Set());
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  const loadFileSubgraph = useCallback(async (fileId: string) => {
    const id = fileId.replace("file_", "");
    setLoading(true); setError("");
    try {
      const data = await fetchGraph(`${JAVA}/api/graph/file/${id}`);
      setGraphData(data);
      setSelectedNode(null); setHighlighted(new Set());
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  // ── Bootstrap ───────────────────────────────────────────────────────────────
  useEffect(() => {
    // Both fns set state in async callbacks; the rule fires because it traces
    // setState inside the called function, but there is no sync cascade.
    /* eslint-disable react-hooks/set-state-in-effect */
    void loadBatchList();
    void loadGraph();
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [loadGraph, loadBatchList]);

  // ── Spread nodes apart so labels don't collide ──────────────────────────────
  // The default force layout packs a batch's files tightly around it, so their
  // labels overlap. Stronger charge repulsion + a longer link distance give each
  // node room for its label.
  useEffect(() => {
    const fg = graphRef.current;
    if (!fg || graphData.nodes.length === 0) return;
    fg.d3Force("charge")?.strength?.(-260);
    fg.d3Force("link")?.distance?.(90);
    fg.d3ReheatSimulation();
  }, [graphData]);

  // ── Resize observer ─────────────────────────────────────────────────────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      const r = entries[0].contentRect;
      if (r.width > 0 && r.height > 0)
        setGraphSize({ w: Math.floor(r.width), h: Math.floor(r.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ── Event handlers ──────────────────────────────────────────────────────────
  const handleSearch = useCallback(() => {
    void loadGraph(search.trim() || undefined, filterStatus || undefined);
  }, [loadGraph, search, filterStatus]);

  const handleClear = useCallback(() => {
    setSearch(""); setFilterStatus("");
    void loadGraph();
  }, [loadGraph]);

  const handleBack = useCallback(() => {
    setViewMode("ALL");
    setSelectedNode(null);
    setHighlighted(new Set());
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
  }, [graphData.links]);

  const handleViewMode = useCallback((m: ViewMode) => {
    setViewMode(m);
    if (m === "ALL") void loadGraph(search.trim() || undefined, filterStatus || undefined);
  }, [loadGraph, search, filterStatus]);

  // ── Derived ─────────────────────────────────────────────────────────────────
  const isListMode = viewMode === "LIST";

  return (
    <div className="flex h-screen bg-slate-950 text-white overflow-hidden">

      {/* ── Left sidebar ───────────────────────────────────────────────────── */}
      <AuditSidebar
        search={search}
        onSearchChange={setSearch}
        onSearch={handleSearch}
        onClear={handleClear}
        viewMode={viewMode}
        onViewMode={handleViewMode}
        onBack={handleBack}
        filterStatus={filterStatus}
        onFilterStatus={setFilterStatus}
        filtersOpen={filtersOpen}
        onToggleFilters={() => setFiltersOpen(o => !o)}
        batches={batches}
        onSelectBatch={loadBatchSubgraph}
        graphData={graphData}
        loading={loading}
        onRefresh={() => void loadGraph(search.trim() || undefined, filterStatus || undefined)}
        showCharts={showCharts}
        onToggleCharts={() => setShowCharts(o => !o)}
      />

      {/* ── Main content ───────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">

        <AuditBreadcrumb
          viewMode={viewMode}
          selectedNode={selectedNode}
          nodeCount={graphData.nodes.length}
          edgeCount={graphData.links.length}
          onBack={handleBack}
        />

        <div className="flex flex-1 overflow-hidden relative">

          {/* ── List view ────────────────────────────────────────────────── */}
          {isListMode ? (
            <AuditListView
              nodes={graphData.nodes}
              onSelectNode={handleNodeClick}
              onDrillBatch={loadBatchSubgraph}
              onDrillFile={loadFileSubgraph}
              onViewMode={handleViewMode}
              search={search}
            />
          ) : (
            /* ── Graph canvas ──────────────────────────────────────────── */
            <div ref={containerRef} className="flex-1 relative bg-[#080C10] overflow-hidden">
              {error && <ErrorOverlay message={error} />}
              {loading && !error && <GraphSkeleton />}

              {!loading && !error && graphData.nodes.length === 0 && (
                <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-600">
                  No data — check the Java API server or try refreshing.
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
                    const lines = [`${node.type.replace(/_/g, " ")}: ${node.label}`, `Status: ${nodeStatusLabel(node.status, node.meta?.fileType as string | undefined)}`];
                    if (node.meta?.reviewer)  lines.push(`Reviewer: ${displayName(String(node.meta.reviewer))}`);
                    if (node.meta?.client)    lines.push(`Client: ${String(node.meta.client)}`);
                    if (node.meta?.fileCount !== undefined) lines.push(`Files: ${String(node.meta.fileCount)}`);
                    return lines.join("\n");
                  }}
                  nodeColor={(n: unknown) => {
                    const node = n as GraphNode;
                    const base = NODE_COLOR[node.type as keyof typeof NODE_COLOR] ?? "#64748b";
                    return (highlighted.size > 0 && !highlighted.has(node.id)) ? base + "28" : base;
                  }}
                  nodeVal={(n: unknown) => NODE_SIZE[(n as GraphNode).type as keyof typeof NODE_SIZE] ?? 6}
                  nodeCanvasObject={(n: unknown, ctx: CanvasRenderingContext2D, globalScale: number) => {
                    const node = n as GraphNode & { x?: number; y?: number };
                    if (node.x == null || node.y == null) return;
                    const size  = NODE_SIZE[node.type as keyof typeof NODE_SIZE] ?? 6;
                    const color = NODE_COLOR[node.type as keyof typeof NODE_COLOR] ?? "#64748b";
                    const dim   = highlighted.size > 0 && !highlighted.has(node.id);
                    ctx.globalAlpha = dim ? 0.12 : 1;
                    ctx.beginPath();
                    ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
                    ctx.fillStyle = color;
                    ctx.fill();
                    if (highlighted.has(node.id) || node.id === selectedNode?.id) {
                      ctx.strokeStyle = "#ffffff55";
                      ctx.lineWidth = 2 / globalScale;
                      ctx.stroke();
                    }
                    ctx.globalAlpha = 1;
                    // Node label at sufficient zoom. Skip dimmed nodes (keeps the
                    // highlighted path legible), draw an ellipsised label on a dark
                    // rounded backdrop so adjacent labels never blur together.
                    if (globalScale > 1.8 && !dim) {
                      const raw = node.label ?? "";
                      const text = raw.length > 22 ? raw.slice(0, 21) + "…" : raw;
                      const fontPx = Math.max(8, 10 / globalScale);
                      ctx.font = `${fontPx}px sans-serif`;
                      ctx.textAlign = "center";
                      ctx.textBaseline = "middle";
                      const padX = 4 / globalScale;
                      const padY = 2 / globalScale;
                      const tw = ctx.measureText(text).width;
                      const lx = node.x;
                      const ly = node.y + size + fontPx + 6 / globalScale;
                      const bw = tw + padX * 2;
                      const bh = fontPx + padY * 2;
                      const r = 3 / globalScale;
                      // Rounded-rect backdrop
                      ctx.fillStyle = "#0b0f14d9";
                      ctx.beginPath();
                      ctx.roundRect(lx - bw / 2, ly - bh / 2, bw, bh, r);
                      ctx.fill();
                      ctx.fillStyle = "#e2e8f0";
                      ctx.fillText(text, lx, ly);
                      ctx.textBaseline = "alphabetic";
                    }
                  }}
                  linkColor={(l: unknown) => EDGE_COLOR[(l as { type: string }).type] ?? "#ffffff14"}
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
                className="absolute bottom-4 right-4 flex h-8 w-8 items-center justify-center rounded-md border border-white/10 bg-[#11161C]/90 text-slate-400 hover:text-white hover:border-white/20 transition-colors"
                title="Fit to view"
              >
                <Maximize2 size={13} />
              </button>

              {/* Hint */}
              {graphData.nodes.length > 0 && !selectedNode && !loading && (
                <p className="absolute bottom-4 left-1/2 -translate-x-1/2 text-[11px] text-slate-700 pointer-events-none select-none">
                  Click any node to inspect · Labels appear at 1.8× zoom
                </p>
              )}
            </div>
          )}

          {/* ── Node detail drawer ──────────────────────────────────────── */}
          {selectedNode && (
            <AuditNodeDrawer
              node={selectedNode}
              links={graphData.links}
              onClose={() => { setSelectedNode(null); setHighlighted(new Set()); }}
              onDrillBatch={loadBatchSubgraph}
              onDrillFile={loadFileSubgraph}
              onViewMode={handleViewMode}
            />
          )}

          {/* ── Analytics charts panel ──────────────────────────────────── */}
          {showCharts && !selectedNode && <AuditChartsPanel />}
        </div>
      </div>
    </div>
  );
}

// ── Helper components ─────────────────────────────────────────────────────────

function ErrorOverlay({ message }: { message: string }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center">
      <div className="rounded-xl border border-red-500/20 bg-red-950/30 px-6 py-5 text-sm text-red-200 text-center max-w-sm">
        <AlertCircle size={22} className="mx-auto mb-3 text-red-400" />
        <p className="font-medium mb-1">Graph load failed</p>
        <p className="text-xs text-red-300/70">{message}</p>
        <p className="mt-2 text-xs text-slate-500">Verify the Java API server is running on port 8080.</p>
      </div>
    </div>
  );
}

function GraphSkeleton() {
  return (
    <div className="flex h-full items-center justify-center pointer-events-none">
      <div className="text-center">
        <div className="relative mx-auto mb-4 h-20 w-20">
          {[0, 1, 2, 3].map(i => (
            <div
              key={i}
              className="absolute inset-0 rounded-full border border-indigo-500/25 animate-ping"
              style={{ animationDelay: `${i * 0.25}s`, animationDuration: "2s" }}
            />
          ))}
          <Network size={28} className="absolute inset-0 m-auto text-indigo-400" />
        </div>
        <p className="text-sm text-slate-400">Building graph…</p>
        <p className="mt-1 text-xs text-slate-600">Fetching nodes and relationships</p>
      </div>
    </div>
  );
}

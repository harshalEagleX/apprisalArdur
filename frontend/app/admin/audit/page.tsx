"use client";
import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import {
  Network, RefreshCw, Maximize2,
  GitBranch, Clock, FileText, AlertCircle, CheckCircle2,
} from "lucide-react";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

// ── Types ─────────────────────────────────────────────────────────────────────
type NodeKind = "BATCH" | "FILE" | "REVIEW_SESSION" | "DECISION" | "RE_REVIEW" | "SUBMIT" | "ASSIGN";
type EdgeKind = "CONTAINS" | "LEADS_TO" | "TRIGGERS" | "ASSIGNS";

interface GraphNode {
  id: string;
  label: string;
  kind: NodeKind;
  meta?: Record<string, string | number | null>;
  x?: number;
  y?: number;
  z?: number;
}

interface GraphEdge {
  source: string;
  target: string;
  kind: EdgeKind;
  label?: string;
}

interface GraphData { nodes: GraphNode[]; links: GraphEdge[] }

interface AuditEntry {
  id: number;
  action: string;
  entityType: string;
  entityId: number;
  details: string;
  createdAt: string;
  user?: { id: number; username: string };
}

interface BatchSummary {
  id: number;
  parentBatchId: string;
  status: string;
  client: { name: string; code: string };
  fileCount: number;
  createdAt: string;
  assignedReviewer?: { username: string };
}

type DimFilter = "all" | "batch" | "file" | "session";

// ── Node colors ───────────────────────────────────────────────────────────────
const NODE_COLOR: Record<NodeKind, string> = {
  BATCH:          "#6366f1",
  FILE:           "#64748b",
  REVIEW_SESSION: "#f59e0b",
  DECISION:       "#22c55e",
  RE_REVIEW:      "#ef4444",
  SUBMIT:         "#06b6d4",
  ASSIGN:         "#a78bfa",
};

const NODE_SIZE: Record<NodeKind, number> = {
  BATCH:          12,
  FILE:           8,
  REVIEW_SESSION: 7,
  DECISION:       5,
  RE_REVIEW:      9,
  SUBMIT:         7,
  ASSIGN:         6,
};

// ── Dynamic ForceGraph (SSR disabled — uses browser canvas APIs) ─────────────
const ForceGraph2D = dynamic(
  () => import("@/components/admin/AuditForceGraph"),
  { ssr: false, loading: () => <GraphSkeleton /> }
);

// ── Build graph from audit logs + batches ────────────────────────────────────
function buildGraph(batches: BatchSummary[], auditMap: Record<number, AuditEntry[]>): GraphData {
  const nodes: GraphNode[] = [];
  const links: GraphEdge[] = [];
  const nodeSet = new Set<string>();

  function addNode(n: GraphNode) {
    if (!nodeSet.has(n.id)) { nodes.push(n); nodeSet.add(n.id); }
  }

  function addEdge(src: string, tgt: string, kind: EdgeKind, label?: string) {
    if (nodeSet.has(src) && nodeSet.has(tgt)) links.push({ source: src, target: tgt, kind, label });
  }

  for (const batch of batches) {
    const batchNodeId = `batch-${batch.id}`;
    addNode({
      id: batchNodeId,
      label: `Batch #${batch.id}\n${batch.client.name}`,
      kind: "BATCH",
      meta: { status: batch.status, client: batch.client.name, files: batch.fileCount },
    });

    if (batch.assignedReviewer) {
      const assignId = `assign-${batch.id}`;
      addNode({ id: assignId, label: `→ ${batch.assignedReviewer.username}`, kind: "ASSIGN" });
      addEdge(batchNodeId, assignId, "ASSIGNS", "assigned");
    }

    const entries = auditMap[batch.id] ?? [];
    const sessionsSeen = new Set<string>();

    for (const entry of entries) {
      const ts = entry.createdAt ? new Date(entry.createdAt).toLocaleTimeString() : "?";
      const who = entry.user?.username ?? "system";

      if (entry.action === "REVIEW_SESSION_STARTED") {
        const sessionId = `session-${entry.entityId}-${entry.id}`;
        if (!sessionsSeen.has(sessionId)) {
          sessionsSeen.add(sessionId);
          addNode({
            id: sessionId,
            label: `Session\n${who} @ ${ts}`,
            kind: "REVIEW_SESSION",
            meta: { user: who, time: ts },
          });
          addEdge(batchNodeId, sessionId, "LEADS_TO", "started review");
        }
      }

      if (entry.action === "REVIEW_DECISION_SAVED") {
        const decisionId = `decision-${entry.id}`;
        const detail = entry.details ?? "";
        const isPass = detail.includes("decision=PASS");
        const ruleId = detail.match(/ruleId=([^,]+)/)?.[1] ?? "rule";
        addNode({
          id: decisionId,
          label: `${isPass ? "✓" : "✗"} ${ruleId}\n${who}`,
          kind: "DECISION",
          meta: { user: who, rule: ruleId, pass: isPass ? "yes" : "no" },
        });
        const parentSession = [...sessionsSeen].findLast(s => s.startsWith(`session-${entry.entityId}`));
        if (parentSession) addEdge(parentSession, decisionId, "LEADS_TO", "decision");
      }

      if (entry.action === "REVIEW_SUBMITTED" || entry.action === "REVIEW_COMPLETE") {
        const submitId = `submit-${entry.id}`;
        addNode({ id: submitId, label: `Submitted\n${who} @ ${ts}`, kind: "SUBMIT", meta: { user: who } });
        const parentSession = [...sessionsSeen].findLast(s => s.startsWith(`session-${entry.entityId}`));
        if (parentSession) addEdge(parentSession, submitId, "LEADS_TO", "submitted");
      }

      if (entry.action === "RE_REVIEW_REQUESTED") {
        const rrId = `rereview-${entry.id}`;
        addNode({ id: rrId, label: `Re-review\n${who} @ ${ts}`, kind: "RE_REVIEW", meta: { user: who } });
        const parentSession = [...sessionsSeen].findLast(s => s.startsWith(`session-${entry.entityId}`));
        const target = parentSession ?? batchNodeId;
        addEdge(target, rrId, "TRIGGERS", "re-review");
      }
    }
  }

  return { nodes, links };
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function AdminAuditPage() {
  const [batches, setBatches]   = useState<BatchSummary[]>([]);
  const [auditMap, setAuditMap] = useState<Record<number, AuditEntry[]>>({});
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState("");
  const [filter, setFilter]     = useState<DimFilter>("all");
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlighted, setHighlighted]   = useState<Set<string>>(new Set());
  const graphRef = useRef<{ zoomToFit: (ms?: number) => void } | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await fetch(`${JAVA}/api/admin/batches?page=0&size=50`, { credentials: "include" });
      if (!res.ok) throw new Error("Failed to load batches");
      const data = await res.json() as { content: BatchSummary[] };
      setBatches(data.content ?? []);

      // Load audit logs for each batch (limited scope)
      const map: Record<number, AuditEntry[]> = {};
      await Promise.allSettled(
        (data.content ?? []).slice(0, 20).map(async (batch: BatchSummary) => {
          const ar = await fetch(`${JAVA}/api/admin/batches/${batch.id}/audit`, { credentials: "include" });
          if (ar.ok) map[batch.id] = await ar.json();
        })
      );
      setAuditMap(map);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const handle = window.setTimeout(() => { void loadData(); }, 0);
    return () => window.clearTimeout(handle);
  }, [loadData]);

  const graphData = useMemo(() => {
    const raw = buildGraph(batches, auditMap);
    if (filter === "all") return raw;
    const keep: NodeKind[] = filter === "batch"
      ? ["BATCH", "ASSIGN"]
      : filter === "file"
        ? ["BATCH", "FILE"]
        : ["REVIEW_SESSION", "DECISION", "SUBMIT", "RE_REVIEW"];
    const keepIds = new Set(raw.nodes.filter(n => keep.includes(n.kind)).map(n => n.id));
    return {
      nodes: raw.nodes.filter(n => keepIds.has(n.id)),
      links: raw.links.filter(l =>
        keepIds.has(typeof l.source === "string" ? l.source : (l.source as GraphNode).id) &&
        keepIds.has(typeof l.target === "string" ? l.target : (l.target as GraphNode).id)
      ),
    };
  }, [batches, auditMap, filter]);

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

  const stats = useMemo(() => ({
    batches: batches.length,
    sessions: graphData.nodes.filter(n => n.kind === "REVIEW_SESSION").length,
    decisions: graphData.nodes.filter(n => n.kind === "DECISION").length,
    reReviews: graphData.nodes.filter(n => n.kind === "RE_REVIEW").length,
    submits: graphData.nodes.filter(n => n.kind === "SUBMIT").length,
  }), [batches, graphData.nodes]);

  return (
    <div className="flex h-screen flex-col bg-slate-950 text-white overflow-hidden">
      {/* Header */}
      <header className="flex h-12 flex-shrink-0 items-center gap-3 border-b border-white/10 bg-[#11161C] px-4">
        <Network size={15} className="text-indigo-400" />
        <span className="text-sm font-semibold text-white">Audit Intelligence Graph</span>
        <div className="flex-1" />
        <div className="flex items-center gap-2">
          {(["all", "batch", "file", "session"] as DimFilter[]).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`h-7 px-2.5 rounded-md text-xs font-medium transition-colors ${filter === f ? "bg-slate-600 text-white" : "text-slate-500 hover:text-slate-300 hover:bg-white/[0.04]"}`}>
              {f === "all" ? "All" : f === "batch" ? "By Batch" : f === "file" ? "By File" : "Sessions"}
            </button>
          ))}
          <button onClick={() => void loadData()} disabled={loading}
            className="flex h-7 items-center gap-1.5 rounded-md border border-white/10 bg-[#11161C] px-2.5 text-xs text-slate-400 hover:text-white">
            <RefreshCw size={11} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </header>

      {/* Stat bar */}
      <div className="flex flex-shrink-0 items-center gap-4 border-b border-white/10 bg-[#0B0F14]/80 px-4 py-2">
        <AuditStat icon={GitBranch}    label="Batches"   value={stats.batches}   color="text-indigo-400" />
        <AuditStat icon={Clock}        label="Sessions"  value={stats.sessions}  color="text-amber-400" />
        <AuditStat icon={CheckCircle2} label="Decisions" value={stats.decisions} color="text-green-400" />
        <AuditStat icon={AlertCircle}  label="Re-reviews" value={stats.reReviews} color="text-red-400" />
        <AuditStat icon={FileText}     label="Submits"   value={stats.submits}   color="text-cyan-400" />
        <div className="ml-auto flex items-center gap-3">
          {/* Legend */}
          {(Object.entries(NODE_COLOR) as [NodeKind, string][]).map(([kind, color]) => (
            <span key={kind} className="flex items-center gap-1 text-[10px] text-slate-500">
              <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: color }} />
              {kind.replace("_", " ")}
            </span>
          ))}
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Graph */}
        <div className="flex-1 relative bg-[#080C10]">
          {error && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="rounded-lg border border-red-500/25 bg-red-950/40 px-6 py-4 text-sm text-red-200 text-center">
                <AlertCircle size={20} className="mx-auto mb-2" />
                {error}
                <div className="mt-2 text-xs text-slate-400">
                  Make sure the admin audit endpoint is available.
                </div>
              </div>
            </div>
          )}
          {loading && !error && <GraphSkeleton />}
          {!loading && !error && (
            <ForceGraph2D
              ref={graphRef as never}
              graphData={graphData as never}
              backgroundColor="#080C10"
              nodeLabel={(n: unknown) => {
                const node = n as GraphNode;
                return `${node.kind}: ${node.label.replace(/\n/g, " ")}`;
              }}
              nodeColor={(n: unknown) => {
                const node = n as GraphNode;
                const dim = highlighted.size > 0 && !highlighted.has(node.id);
                const base = NODE_COLOR[node.kind] ?? "#64748b";
                return dim ? base + "33" : base;
              }}
              nodeVal={(n: unknown) => NODE_SIZE[(n as GraphNode).kind] ?? 6}
              nodeCanvasObject={(n: unknown, ctx: CanvasRenderingContext2D, globalScale: number) => {
                const node = n as GraphNode & { x?: number; y?: number };
                if (node.x == null || node.y == null) return;
                const size = NODE_SIZE[node.kind] ?? 6;
                const dim = highlighted.size > 0 && !highlighted.has(node.id);
                ctx.globalAlpha = dim ? 0.18 : 1;
                ctx.beginPath();
                ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
                ctx.fillStyle = NODE_COLOR[node.kind] ?? "#64748b";
                ctx.fill();
                if (highlighted.has(node.id)) {
                  ctx.strokeStyle = "#ffffff55";
                  ctx.lineWidth = 1.5;
                  ctx.stroke();
                }
                const label = node.label.split("\n")[0];
                const fontSize = Math.max(8, 12 / globalScale);
                ctx.font = `${fontSize}px sans-serif`;
                ctx.fillStyle = dim ? "#ffffff22" : "#e2e8f0";
                ctx.textAlign = "center";
                ctx.fillText(label, node.x, node.y + size + fontSize * 0.9);
                ctx.globalAlpha = 1;
              }}
              linkColor={() => "#ffffff18"}
              linkWidth={1}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={1}
              onNodeClick={handleNodeClick as never}
              onBackgroundClick={() => { setSelectedNode(null); setHighlighted(new Set()); }}
              cooldownTicks={80}
            />
          )}

          {/* Zoom controls */}
          <div className="absolute bottom-4 right-4 flex flex-col gap-1">
            <button onClick={() => (graphRef.current as { zoomToFit?: (ms: number) => void })?.zoomToFit?.(400)}
              className="flex h-8 w-8 items-center justify-center rounded-md border border-white/10 bg-[#11161C] text-slate-400 hover:text-white">
              <Maximize2 size={13} />
            </button>
          </div>
        </div>

        {/* Node detail panel */}
        {selectedNode && (
          <div className="w-64 flex-shrink-0 border-l border-white/10 bg-[#11161C] p-4 overflow-y-auto">
            <div className="flex items-center gap-2 mb-3">
              <span className="inline-block w-3 h-3 rounded-full flex-shrink-0"
                style={{ background: NODE_COLOR[selectedNode.kind] }} />
              <span className="text-xs font-semibold text-white uppercase tracking-wide">{selectedNode.kind.replace("_", " ")}</span>
            </div>
            <div className="text-sm font-medium text-slate-200 leading-snug whitespace-pre-line mb-3">
              {selectedNode.label}
            </div>
            {selectedNode.meta && (
              <div className="space-y-1.5">
                {Object.entries(selectedNode.meta).map(([k, v]) => (
                  <div key={k} className="flex items-start gap-2">
                    <span className="text-[10px] uppercase tracking-wide text-slate-500 w-16 flex-shrink-0">{k}</span>
                    <span className="text-[11px] text-slate-300 break-all">{String(v ?? "—")}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4 flex items-center gap-2 text-[10px] text-slate-500">
              <span className="inline-block w-2 h-2 rounded-full" style={{ background: NODE_COLOR[selectedNode.kind] }} />
              {highlighted.size - 1} connected node{highlighted.size !== 2 ? "s" : ""}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function AuditStat({ icon: Icon, label, value, color }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string; value: number; color: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <Icon size={12} className={color} />
      <span className="text-xs text-slate-300 tabular-nums font-medium">{value}</span>
      <span className="text-[10px] text-slate-600 uppercase tracking-wide">{label}</span>
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
        <div className="text-sm text-slate-400">Loading audit graph…</div>
        <div className="mt-1 text-xs text-slate-600">Building node relationships</div>
      </div>
    </div>
  );
}

"use client";
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { ArrowLeft, ChevronDown, ChevronUp, Check, X, AlertTriangle, CheckCircle2, Crosshair, ZoomIn, ZoomOut } from "lucide-react";
import { getQCRules, getQCProgress, saveDecision, getPdfUrl, getQCFileInfo, getRealtimeUrl, startReviewSession, heartbeatReviewSession, type BatchFile, type QCRuleResult } from "@/lib/api";
import { PageSpinner } from "@/components/shared/Spinner";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";
const PdfDocumentViewer = dynamic(() => import("./PdfDocumentViewer"), {
  ssr: false,
  loading: () => <PageSpinner label="Loading document viewer..." />,
});

type Decision = "PASS" | "FAIL";
type Filter = "all" | "fail" | "verify" | "pass";
type RuleFocus = {
  ruleId: string;
  page: number;
  documentType: string;
  note: string;
  bbox?: { x: number; y: number; w: number; h: number } | null;
  located: boolean;
};
type ReviewProgress = { pending: number; canSubmit: boolean; totalToVerify: number };

const STATUS_STYLE: Record<string, { border: string; bg: string; text: string }> = {
  pass:         { border: "border-green-800/40",  bg: "bg-green-950/20",  text: "text-green-300" },
  fail:         { border: "border-red-800/40",    bg: "bg-red-950/20",    text: "text-red-300" },
  verify:       { border: "border-amber-800/40",  bg: "bg-amber-950/20",  text: "text-amber-300" },
  MANUAL_PASS:  { border: "border-teal-800/40",   bg: "bg-teal-950/20",   text: "text-teal-300" },
};
const SEV_STYLE: Record<string, string> = {
  BLOCKING: "bg-red-950/60 border-red-800/50 text-red-400",
  STANDARD: "bg-slate-800 border-slate-700 text-slate-400",
  ADVISORY: "bg-slate-800/50 border-slate-700/50 text-slate-500",
};

function ruleStatus(status: string) {
  return status === "MANUAL_PASS" ? status : status.toLowerCase();
}

function focusForRule(rule: QCRuleResult): RuleFocus {
  const ruleId = rule.ruleId;
  const backendPage = typeof rule.pdfPage === "number" && rule.pdfPage > 0 ? rule.pdfPage : null;
  const hasBox = [rule.bboxX, rule.bboxY, rule.bboxW, rule.bboxH].every(value => typeof value === "number");

  if (!backendPage) {
    console.warn(`Rule ${rule.ruleId} has no pdfPage — bbox unavailable`);
    return {
      ruleId,
      page: 1,
      documentType: "APPRAISAL",
      note: "Location not yet extracted",
      bbox: null,
      located: false,
    };
  }

  return {
    ruleId,
    page: backendPage,
    documentType: "APPRAISAL",
    note: hasBox ? "OCR evidence location" : "Page located; field box unavailable",
    bbox: hasBox
      ? { x: rule.bboxX as number, y: rule.bboxY as number, w: rule.bboxW as number, h: rule.bboxH as number }
      : null,
    located: true,
  };
}

export default function VerifyFilePage() {
  const { id } = useParams<{ id: string }>();
  const qcResultId = Number(id);
  const [rules, setRules]         = useState<QCRuleResult[]>([]);
  const [loading, setLoading]     = useState(true);
  const [filter, setFilter]       = useState<Filter>("all");
  const [decisions, setDecisions] = useState<Record<number, Decision>>({});
  const [comments, setComments]   = useState<Record<number, string>>({});
  const [saving, setSaving]       = useState<number | null>(null);
  const [saved, setSaved]         = useState<Set<number>>(new Set());
  const [progress, setProgress]   = useState<ReviewProgress | null>(null);
  const [realtimeConnected, setRealtimeConnected] = useState(false);
  const [documents, setDocuments] = useState<BatchFile[]>([]);
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null);
  const [pdfError, setPdfError]   = useState(false);
  const [activeFocus, setActiveFocus] = useState<RuleFocus | null>(null);
  const [activePage, setActivePage] = useState(1);
  const [pageCount, setPageCount] = useState<number | null>(null);
  const [viewerWidth, setViewerWidth] = useState(720);
  const [zoom, setZoom] = useState(1);
  const [highlighting, setHighlighting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [acknowledged, setAcknowledged] = useState<Record<number, boolean>>({});
  const viewerRef = useRef<HTMLDivElement | null>(null);

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const [rulesData, prog] = await Promise.all([getQCRules(qcResultId), getQCProgress(qcResultId)]);
      setRules(rulesData.map(r => ({ ...r, status: ruleStatus(r.status) }))); setProgress(prog);
      const dec: Record<number, Decision> = {}; const com: Record<number, string> = {};
      for (const r of rulesData) {
        if (r.reviewerVerified === true)  dec[r.id] = "PASS";
        if (r.reviewerVerified === false) dec[r.id] = "FAIL";
        if (r.reviewerComment) com[r.id] = r.reviewerComment;
      }
      setDecisions(dec); setComments(com);
    } finally { setLoading(false); }
  }, [qcResultId]);

  useEffect(() => {
    const markOnline = () => setOffline(false);
    const markOffline = () => setOffline(true);
    setOffline(typeof navigator !== "undefined" ? !navigator.onLine : false);
    window.addEventListener("online", markOnline);
    window.addEventListener("offline", markOffline);
    return () => {
      window.removeEventListener("online", markOnline);
      window.removeEventListener("offline", markOffline);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    startReviewSession(qcResultId)
      .then(session => {
        if (cancelled) return;
        setSessionToken(session.sessionToken);
        setSessionError(session.lockAcknowledged ? "Continuing a report that had prior review activity. Review existing decisions before sign-off." : null);
      })
      .catch(error => {
        if (cancelled) return;
        setSessionError(error instanceof Error ? error.message : "Unable to start review session.");
      });
    return () => { cancelled = true; };
  }, [qcResultId]);

  useEffect(() => {
    if (!sessionToken) return;
    const timer = window.setInterval(() => {
      heartbeatReviewSession(qcResultId, sessionToken).catch(error => {
        setSessionError(error instanceof Error ? error.message : "Review session timed out. Reload to resume.");
      });
    }, 120_000);
    return () => window.clearInterval(timer);
  }, [qcResultId, sessionToken]);

  useEffect(() => {
    getQCFileInfo(qcResultId)
      .then(d => {
        const docs = d.documents?.length ? d.documents : d.batchFile ? [d.batchFile] : [];
        setDocuments(docs);
        setActiveDocumentId(d.batchFile?.id ?? docs[0]?.id ?? null);
        setPdfError(docs.length === 0);
      })
      .catch(() => setPdfError(true));
  }, [qcResultId]);

  const activeDocument = useMemo(
    () => documents.find(doc => doc.id === activeDocumentId) ?? documents[0],
    [documents, activeDocumentId]
  );
  const activeDocumentUrl = activeDocument ? getPdfUrl(activeDocument.id) : undefined;

  useEffect(() => {
    if (!viewerRef.current) return;
    const observer = new ResizeObserver(entries => {
      const width = entries[0]?.contentRect.width;
        if (width) setViewerWidth(Math.max(320, Math.floor(width - 48)));
    });
    observer.observe(viewerRef.current);
    return () => observer.disconnect();
  }, []);

  function focusRule(rule: QCRuleResult) {
    const nextFocus = focusForRule(rule);
    if (!nextFocus.located) {
      setActiveFocus(nextFocus);
      setHighlighting(false);
      return;
    }
    const preferredDoc = documents.find(doc => doc.fileType === nextFocus.documentType) ?? documents.find(doc => doc.fileType === "APPRAISAL") ?? documents[0];
    if (preferredDoc) setActiveDocumentId(preferredDoc.id);
    setActiveFocus(nextFocus);
    setActivePage(nextFocus.page);
    setHighlighting(true);
    window.setTimeout(() => setHighlighting(false), 2600);
  }

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadRules(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadRules]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let closed = false;
    const progressTopic = `/topic/reviewer/qc/${qcResultId}/progress`;
    const decisionTopic = `/topic/reviewer/qc/${qcResultId}/decision`;

    const connect = () => {
      ws = new WebSocket(getRealtimeUrl());
      ws.onopen = () => {
        setRealtimeConnected(true);
        ws?.send(`subscribe:${progressTopic}`);
        ws?.send(`subscribe:${decisionTopic}`);
      };
      ws.onclose = () => {
        setRealtimeConnected(false);
        if (!closed) {
          reconnectTimer = window.setTimeout(connect, 2500);
        }
      };
      ws.onerror = () => {
        setRealtimeConnected(false);
      };
      ws.onmessage = event => {
        try {
          const message = JSON.parse(event.data) as { topic?: string; payload?: unknown };
          if (message.topic === progressTopic && message.payload && typeof message.payload === "object") {
            const next = message.payload as ReviewProgress;
            setProgress({
              pending: Number(next.pending ?? 0),
              canSubmit: Boolean(next.canSubmit),
              totalToVerify: Number(next.totalToVerify ?? 0),
            });
          }
          if (message.topic === decisionTopic) {
            void loadRules();
          }
        } catch {
          // Ignore malformed realtime messages; REST polling remains the fallback.
        }
      };
    };

    connect();
    return () => {
      closed = true;
      setRealtimeConnected(false);
      if (reconnectTimer != null) window.clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [loadRules, qcResultId]);

  async function handleDecision(rule: QCRuleResult, decision: Decision) {
    if (!sessionToken) {
      setSessionError("Review session is not ready yet.");
      return;
    }
    if (offline) {
      setSessionError("You're offline. Decisions cannot be saved until your connection is restored.");
      return;
    }
    const presentedAt = rule.firstPresentedAt ? new Date(rule.firstPresentedAt).getTime() : Date.now();
    const latencyMs = Math.max(0, Date.now() - presentedAt);
    setSaving(rule.id);
    try {
      await saveDecision(rule.id, decision, comments[rule.id], sessionToken, latencyMs, Boolean(acknowledged[rule.id]));
      setDecisions(prev => ({ ...prev, [rule.id]: decision }));
      setSaved(prev => new Set(prev).add(rule.id));
      const prog = await getQCProgress(qcResultId); setProgress(prog);
      void loadRules();
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : "Decision was not saved. Try again.");
    }
    finally { setSaving(null); }
  }

  async function handleSubmit() {
    if (!sessionToken) {
      setSessionError("Review session is not ready yet.");
      return;
    }
    const freshProgress = await getQCProgress(qcResultId);
    setProgress(freshProgress);
    if (!freshProgress.canSubmit) {
      setSessionError(`There are still ${freshProgress.pending} item(s) waiting for server-confirmed decisions.`);
      return;
    }
    const expected = String(qcResultId).slice(-4);
    const typed = window.prompt(`You are about to sign off on this report. Type the last 4 digits of QC Result #${qcResultId} to confirm.`);
    if (typed !== expected) {
      setSessionError("Sign-off cancelled. The confirmation digits did not match.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch(`${JAVA}/api/reviewer/qc/${qcResultId}/submit`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: "", sessionToken }),
      });
      if (!response.ok) throw new Error("Review submit failed");
      window.location.href = "/reviewer/queue";
    } finally { setSubmitting(false); }
  }

  const counts = {
    total:  rules.length,
    pass:   rules.filter(r => r.status === "pass" || r.status === "MANUAL_PASS").length,
    fail:   rules.filter(r => r.status === "fail").length,
    review: rules.filter(r => r.status === "verify").length,
  };
  const filtered = rules.filter(r => {
    if (filter === "fail")   return r.status === "fail";
    if (filter === "verify") return r.status === "verify";
    if (filter === "pass")   return r.status === "pass" || r.status === "MANUAL_PASS";
    return true;
  });
  const reviewedCount  = (progress?.totalToVerify ?? 0) - (progress?.pending ?? 0);
  const reviewProgress = progress?.totalToVerify ? Math.round((reviewedCount / progress.totalToVerify) * 100) : 0;

  return (
    <div className="h-screen flex flex-col bg-slate-950 text-white overflow-hidden">
      {(offline || sessionError) && (
        <div className={`px-4 py-2 text-xs border-b ${offline ? "bg-red-950/60 border-red-800/50 text-red-200" : "bg-amber-950/60 border-amber-800/50 text-amber-100"}`}>
          {offline ? "You're offline. Decisions are frozen until the connection is restored." : sessionError}
        </div>
      )}
      {/* Top bar */}
      <header className="flex-shrink-0 flex items-center gap-3 px-4 h-12 bg-slate-900 border-b border-slate-800">
        <a href="/reviewer/queue" className="flex items-center gap-1.5 text-slate-400 hover:text-white text-sm transition-colors flex-shrink-0">
          <ArrowLeft size={14} /> Queue
        </a>
        <div className="w-px h-4 bg-slate-700 flex-shrink-0" />
        <span className="text-sm font-medium text-slate-300 truncate flex-1">QC Result #{qcResultId}</span>
        <div className="hidden sm:flex items-center gap-2 flex-shrink-0">
          <CountBadge label="Pass"   count={counts.pass}   style="text-green-400 bg-green-950/50 border-green-800/50" />
          <CountBadge label="Fail"   count={counts.fail}   style="text-red-400   bg-red-950/50   border-red-800/50" />
          <CountBadge label="Needs Review" count={counts.review} style="text-amber-400 bg-amber-950/50 border-amber-800/50" />
        </div>
        {progress && progress.totalToVerify > 0 && (
          <div className="hidden md:flex items-center gap-2 flex-shrink-0">
            <div className="w-20 h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${reviewProgress}%` }} />
            </div>
            <span className="text-[11px] text-slate-500 font-mono">{reviewedCount}/{progress.totalToVerify}</span>
            <span className={`h-1.5 w-1.5 rounded-full ${realtimeConnected ? "bg-green-400" : "bg-slate-600"}`} title={realtimeConnected ? "Live updates connected" : "Live updates reconnecting"} />
          </div>
        )}
        <button onClick={handleSubmit} disabled={!progress?.canSubmit || submitting}
          className="flex-shrink-0 flex items-center gap-1.5 h-8 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-xs font-semibold transition-colors">
          {submitting ? <svg className="animate-spin h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> : null}
          {submitting ? "Submitting…" : progress?.pending ? `Submit (${progress.pending} left)` : "Submit review"}
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* PDF */}
        <div className="w-[55%] flex-shrink-0 border-r border-slate-800 flex flex-col">
          <div className="flex-shrink-0 px-4 py-2 border-b border-slate-800 flex items-center gap-2">
            <svg className="w-3.5 h-3.5 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span className="text-xs text-slate-500 flex-shrink-0">Documents</span>
            <div className="flex items-center gap-1 overflow-x-auto">
              {documents.map(doc => (
                <button key={doc.id} onClick={() => { setActiveDocumentId(doc.id); setPageCount(null); setPdfError(false); setActiveFocus(null); setActivePage(1); }}
                  className={`h-7 px-2 rounded-md text-[11px] font-medium border transition-colors whitespace-nowrap ${
                    activeDocument?.id === doc.id
                      ? "bg-blue-600/20 border-blue-500/50 text-blue-200"
                      : "bg-slate-900 border-slate-800 text-slate-500 hover:text-slate-300"
                  }`}>
                  {doc.fileType === "APPRAISAL" ? "Report" : doc.fileType === "ENGAGEMENT" ? "Order" : doc.fileType === "CONTRACT" ? "Contract" : "PDF"}
                </button>
              ))}
            </div>
            {activeDocument && (
              <div className="ml-auto flex items-center gap-1 text-[11px] text-slate-500">
                <button
                  onClick={() => setZoom(value => Math.max(0.6, Math.round((value - 0.1) * 10) / 10))}
                  disabled={zoom <= 0.6}
                  className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-slate-800 bg-slate-900 text-slate-400 disabled:opacity-30 hover:text-white"
                  title="Zoom out"
                >
                  <ZoomOut size={13} />
                </button>
                <button
                  onClick={() => setZoom(1)}
                  className="h-7 min-w-12 rounded-md border border-slate-800 bg-slate-900 px-2 font-mono text-slate-400 hover:text-white"
                  title="Reset zoom"
                >
                  {Math.round(zoom * 100)}%
                </button>
                <button
                  onClick={() => setZoom(value => Math.min(1.8, Math.round((value + 0.1) * 10) / 10))}
                  disabled={zoom >= 1.8}
                  className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-slate-800 bg-slate-900 text-slate-400 disabled:opacity-30 hover:text-white"
                  title="Zoom in"
                >
                  <ZoomIn size={13} />
                </button>
              </div>
            )}
          </div>
          {activeDocument ? (
            <div ref={viewerRef} className={`relative flex-1 overflow-auto bg-slate-950 ${highlighting ? "ring-2 ring-amber-400 ring-inset" : ""}`}>
              {activeFocus && (
                <div className={`absolute left-4 top-4 z-10 max-w-sm rounded-lg border px-3 py-2 shadow-xl transition-opacity ${
                  highlighting ? "opacity-100 bg-amber-400/95 border-amber-200 text-slate-950" : "opacity-80 bg-slate-900/95 border-slate-700 text-slate-200"
                }`}>
                  <div className="flex items-center gap-2 text-xs font-semibold">
                    <Crosshair size={13} />
                    {activeFocus.ruleId}
                  </div>
                  <div className="mt-0.5 text-[11px] opacity-80">{activeFocus.note}</div>
                  {!activeFocus.located && (
                    <div className="mt-1 text-[11px] text-amber-300">Re-run QC after location extraction is available.</div>
                  )}
                </div>
              )}
              <div className="min-h-full flex justify-center px-4 py-12">
                <div className="relative">
                  <PdfDocumentViewer
                    key={activeDocument.id}
                    fileUrl={activeDocumentUrl}
                    targetPage={activePage}
                    targetBox={activeFocus?.bbox ?? null}
                    width={Math.round(viewerWidth * zoom)}
                    highlighting={highlighting}
                    onLoadSuccess={(numPages) => {
                      setPageCount(numPages);
                      setPdfError(false);
                      setActivePage(page => Math.min(Math.max(page, 1), numPages));
                    }}
                    onLoadError={() => setPdfError(true)}
                  />
                </div>
              </div>
            </div>
          ) : pdfError ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-500">
              <AlertTriangle size={18} className="text-amber-500" />
              <span className="text-sm">Document unavailable</span>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <svg className="animate-spin h-6 w-6 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
            </div>
          )}
        </div>

        {/* Rules */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-shrink-0 flex items-center gap-1 px-3 py-2 border-b border-slate-800">
            {(["all","fail","verify","pass"] as Filter[]).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={`h-7 px-2.5 rounded-md text-xs font-medium transition-colors ${
                  filter === f ? "bg-blue-600 text-white" : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
                }`}>
                {f === "all" ? `All (${counts.total})` : f === "fail" ? `Fail (${counts.fail})` : f === "verify" ? `Needs Review (${counts.review})` : `Pass (${counts.pass})`}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {loading ? <PageSpinner label="Loading rules…" /> : filtered.length === 0 ? (
              <div className="text-center text-slate-500 py-10 text-sm">No rules match this filter</div>
            ) : filtered.map(rule => (
              <RuleCard key={rule.id} rule={rule} decision={decisions[rule.id]} comment={comments[rule.id] ?? ""}
                saving={saving === rule.id} savedNow={saved.has(rule.id)}
                offline={offline} sessionReady={Boolean(sessionToken)}
                acknowledged={Boolean(acknowledged[rule.id])}
                active={activeFocus?.ruleId === rule.ruleId}
                onSelect={() => focusRule(rule)}
                onDecision={d => handleDecision(rule, d)}
                onAcknowledge={checked => setAcknowledged(prev => ({ ...prev, [rule.id]: checked }))}
                onComment={c => setComments(prev => ({ ...prev, [rule.id]: c }))} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function CountBadge({ label, count, style }: { label: string; count: number; style: string }) {
  return <span className={`text-[11px] px-2 py-0.5 rounded-md border font-medium ${style}`}>{count} {label}</span>;
}

function RuleCard({ rule, decision, comment, saving, savedNow, offline, sessionReady, acknowledged, active, onSelect, onDecision, onAcknowledge, onComment }: {
  rule: QCRuleResult; decision?: Decision; comment: string; saving: boolean; savedNow: boolean;
  offline: boolean; sessionReady: boolean; acknowledged: boolean;
  active?: boolean; onSelect: () => void; onDecision: (d: Decision) => void; onAcknowledge: (checked: boolean) => void; onComment: (c: string) => void;
}) {
  const normalizedStatus = ruleStatus(rule.status);
  const [expanded, setExpanded] = useState(normalizedStatus === "fail" || normalizedStatus === "verify");
  const [now, setNow] = useState(Date.now());
  const mountedAt = useRef(Date.now());
  const s = STATUS_STYLE[normalizedStatus] ?? STATUS_STYLE["verify"];
  const sev = rule.severity ?? "STANDARD";
  const isVerify = normalizedStatus === "verify";
  const isFail = normalizedStatus === "fail";
  const isBlockingVerify = isVerify && sev === "BLOCKING";
  const presentedAt = rule.firstPresentedAt ? new Date(rule.firstPresentedAt).getTime() : mountedAt.current;
  const elapsedMs = Math.max(0, now - presentedAt);
  const waitMs = isVerify ? Math.max(0, 8000 - elapsedMs) : 0;
  const waitSeconds = Math.ceil(waitMs / 1000);
  const overrideReasonOk = !isFail || comment.trim().length >= 20;
  const canAct = sessionReady && !offline && !saving && waitMs === 0 && (!isBlockingVerify || acknowledged);
  const canPass = canAct && overrideReasonOk;
  const canFail = canAct && isVerify;

  useEffect(() => {
    if (!isVerify || waitMs === 0) return;
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [isVerify, waitMs]);

  return (
    <div className={`rounded-xl border p-3 ${s.border} ${s.bg} ${active ? "ring-1 ring-amber-400/70" : ""}`}>
      <button onClick={() => { setExpanded(!expanded); onSelect(); }} className="w-full text-left">
        <div className="flex items-start gap-2">
          <span className="font-mono text-[10px] bg-slate-800/60 border border-slate-700/40 px-1.5 py-0.5 rounded text-slate-400 flex-shrink-0 mt-0.5">{rule.ruleId}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs font-medium text-slate-200">{rule.ruleName}</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${SEV_STYLE[sev] ?? SEV_STYLE.STANDARD}`}>{sev}</span>
              {savedNow && <span className="text-[10px] text-teal-400 flex items-center gap-0.5"><CheckCircle2 size={9} />saved</span>}
              {rule.overridePending && <span className="text-[10px] text-blue-300 border border-blue-800/50 bg-blue-950/40 rounded px-1.5 py-0.5">second approval pending</span>}
            </div>
            <p className={`text-xs mt-0.5 leading-relaxed ${s.text} opacity-80 line-clamp-2`}>
              {normalizedStatus === "verify" && rule.verifyQuestion ? rule.verifyQuestion : normalizedStatus === "fail" && rule.rejectionText ? rule.rejectionText : rule.message}
            </p>
          </div>
          <div className="flex-shrink-0 text-slate-600">{expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}</div>
        </div>
      </button>

      {expanded && (
        <div className="mt-3 space-y-2.5">
          {(rule.appraisalValue || rule.engagementValue) && (
            <div className="grid grid-cols-2 gap-2">
              {rule.appraisalValue && (
                <div className="bg-slate-800/50 rounded-lg p-2.5">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 mb-1">Found in report</div>
                  <div className="font-mono text-xs text-slate-300 break-all leading-relaxed">{rule.appraisalValue}</div>
                </div>
              )}
              {rule.engagementValue && (
                <div className="bg-blue-950/30 border border-blue-800/30 rounded-lg p-2.5">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-blue-500 mb-1">Expected (order form)</div>
                  <div className="font-mono text-xs text-blue-300 break-all leading-relaxed">{rule.engagementValue}</div>
                </div>
              )}
            </div>
          )}
          {rule.actionItem && (
            <div className="flex items-start gap-2 bg-amber-950/20 border border-amber-800/20 rounded-lg p-2.5 text-xs text-amber-300">
              <AlertTriangle size={11} className="flex-shrink-0 mt-0.5" />
              <span className="leading-relaxed">{rule.actionItem}</span>
            </div>
          )}
          {rule.confidence != null && (
            <div className="text-[11px] text-slate-500 font-mono">
              Confidence {Math.round(Number(rule.confidence) * 100)}%
            </div>
          )}
          {isVerify && (
            <details className="rounded-lg border border-slate-800 bg-slate-900/60 px-2.5 py-2 text-xs text-slate-400">
              <summary className="cursor-pointer text-slate-300 font-medium">Rule help</summary>
              <div className="mt-2 space-y-2 leading-relaxed">
                <p>{rule.help?.summary ?? "Review the referenced values and document location before choosing Pass or Fail."}</p>
                {rule.help?.example && (
                  <p className="text-slate-500">{rule.help.example}</p>
                )}
                {rule.help?.terms && Object.keys(rule.help.terms).length > 0 && (
                  <div className="grid gap-1">
                    {Object.entries(rule.help.terms).map(([term, meaning]) => (
                      <div key={term} className="flex gap-2">
                        <span className="font-mono text-slate-300 min-w-16">{term}</span>
                        <span>{meaning}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </details>
          )}
          {rule.reviewRequired ? (
            <div className="space-y-2">
              {isVerify && waitMs > 0 && (
                <div className="text-[11px] text-amber-300 bg-amber-950/20 border border-amber-800/30 rounded-lg px-2.5 py-2">
                  Read the question and document reference. Actions unlock in {waitSeconds}s.
                </div>
              )}
              {isBlockingVerify && (
                <label className="flex items-start gap-2 text-[11px] text-slate-300 bg-slate-900/70 border border-slate-800 rounded-lg px-2.5 py-2">
                  <input type="checkbox" checked={acknowledged} onChange={e => onAcknowledge(e.target.checked)} className="mt-0.5" />
                  <span>I have reviewed the referenced document sections.</span>
                </label>
              )}
              {isFail && (
                <div className="text-[11px] text-red-200 bg-red-950/20 border border-red-800/30 rounded-lg px-2.5 py-2">
                  PASS here is an override. Enter a specific reason of at least 20 characters; a second reviewer must approve it before sign-off.
                </div>
              )}
              {rule.overridePending && (
                <div className="text-[11px] text-blue-200 bg-blue-950/20 border border-blue-800/30 rounded-lg px-2.5 py-2">
                  Override requested by {rule.overrideRequestedBy ?? "another reviewer"}. A different reviewer must press Pass to approve it.
                </div>
              )}
              <div className="flex gap-2">
                <button onClick={() => onDecision("PASS")} disabled={!canPass}
                  className={`flex-1 flex items-center justify-center gap-1.5 h-8 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 ${decision === "PASS" ? "bg-green-600 text-white" : "bg-slate-800 hover:bg-green-900/40 hover:text-green-300 text-slate-400 border border-slate-700"}`}>
                  {saving ? <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> : <Check size={12} />} Pass
                </button>
                {normalizedStatus === "verify" && (
                  <button onClick={() => onDecision("FAIL")} disabled={!canFail}
                    className={`flex-1 flex items-center justify-center gap-1.5 h-8 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 ${decision === "FAIL" ? "bg-red-600 text-white" : "bg-slate-800 hover:bg-red-900/40 hover:text-red-300 text-slate-400 border border-slate-700"}`}>
                    {saving ? <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> : <X size={12} />} Fail
                  </button>
                )}
              </div>
              <textarea value={comment} onChange={e => onComment(e.target.value)}
                onBlur={() => decision && onDecision(decision)}
                placeholder={isFail ? "Reason for override - be specific (minimum 20 characters)." : "Add a comment (optional)..."} rows={2}
                className="w-full bg-slate-800/50 border border-slate-700/40 rounded-lg px-2.5 py-2 text-xs text-slate-300 placeholder-slate-600 resize-none focus:outline-none focus:ring-1 focus:ring-blue-600/50 transition-colors" />
            </div>
          ) : (
            <div className={`flex items-center gap-1.5 text-xs ${s.text} opacity-60`}>
              {normalizedStatus === "pass" || normalizedStatus === "MANUAL_PASS"
                ? <><CheckCircle2 size={11} /> No action required</>
                : null}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

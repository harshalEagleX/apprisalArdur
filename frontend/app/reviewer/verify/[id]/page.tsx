"use client";
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { useParams, useSearchParams } from "next/navigation";
import {
  ArrowLeft, ChevronDown, ChevronUp, Check, X, AlertTriangle, CheckCircle2,
  Crosshair, ZoomIn, ZoomOut, Cloud, WifiOff, ArrowDownCircle, Search,
} from "lucide-react";
import {
  getQCRules, getQCProgress, saveDecision, getPdfUrl, getQCFileInfo,
  type BatchFile, type QCRuleResult,
} from "@/lib/api";
import { PageSpinner } from "@/components/shared/Spinner";
import DeviceGate from "@/components/shared/DeviceGate";
import { RuleCard } from "@/components/reviewer/RuleCard";
import { SignOffDialog } from "@/components/reviewer/SignOffDialog";
import { useReviewSession } from "@/hooks/useReviewSession";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

const PdfDocumentViewer = dynamic(() => import("./PdfDocumentViewer"), {
  ssr: false,
  loading: () => <PageSpinner label="Loading document viewer..." />,
});

type Decision = "PASS" | "FAIL";
type Filter = "all" | "fail" | "verify" | "pass";
const FILTERS: Filter[] = ["all", "fail", "verify", "pass"];

type RuleFocus = {
  ruleId: string; page: number; documentType: string; note: string;
  bbox?: { x: number; y: number; w: number; h: number } | null;
  located: boolean;
};
type ReviewProgress = { pending: number; canSubmit: boolean; totalToVerify: number };
type DecisionEvent = {
  ruleResultId: number; decision: Decision; savedAt: string; status: string;
  reviewerVerified?: boolean | null; overridePending?: boolean; reviewerComment?: string;
};

const STATUS_STYLE: Record<string, { border: string; bg: string; text: string }> = {
  pass:        { border: "border-green-800/40",  bg: "bg-green-950/20",  text: "text-green-300" },
  fail:        { border: "border-red-800/40",    bg: "bg-red-950/20",    text: "text-red-300" },
  verify:      { border: "border-amber-800/40",  bg: "bg-amber-950/20",  text: "text-amber-300" },
  MANUAL_PASS: { border: "border-teal-800/40",   bg: "bg-teal-950/20",   text: "text-teal-300" },
};

function ruleStatus(status: string) {
  const n = status.toLowerCase();
  return n === "manual_pass" ? "MANUAL_PASS" : n;
}

function focusForRule(rule: QCRuleResult): RuleFocus {
  const backendPage = typeof rule.pdfPage === "number" && rule.pdfPage > 0 ? rule.pdfPage : null;
  const hasBox = [rule.bboxX, rule.bboxY, rule.bboxW, rule.bboxH].every(v => typeof v === "number");
  if (!backendPage) {
    return { ruleId: rule.ruleId, page: 1, documentType: "APPRAISAL", note: "Location not yet extracted", bbox: null, located: false };
  }
  return {
    ruleId: rule.ruleId, page: backendPage, documentType: "APPRAISAL",
    note: hasBox ? "OCR evidence location" : "Page located; field box unavailable",
    bbox: hasBox ? { x: rule.bboxX as number, y: rule.bboxY as number, w: rule.bboxW as number, h: rule.bboxH as number } : null,
    located: true,
  };
}

function safeReviewerQueuePath(value: string | null) {
  if (!value) return "/reviewer/queue";
  try {
    const decoded = decodeURIComponent(value);
    return decoded.startsWith("/reviewer/queue") ? decoded : "/reviewer/queue";
  } catch {
    return value.startsWith("/reviewer/queue") ? value : "/reviewer/queue";
  }
}

function CountBadge({ label, count, style }: { label: string; count: number; style: string }) {
  return <span className={`text-[11px] px-2 py-0.5 rounded-md border font-medium ${style}`}>{count} {label}</span>;
}

function RuleFocusOverlay({ focus, highlighting }: { focus: RuleFocus; highlighting: boolean }) {
  return (
    <div className={`pointer-events-none fixed left-3 top-3 z-50 max-w-[180px] rounded-md border px-2 py-1 text-[10px] shadow-lg transition-colors ${highlighting ? "bg-amber-300/95 border-amber-100 text-slate-950" : "bg-slate-900/95 border-slate-700 text-slate-200 opacity-90"}`}>
      <div className="flex items-center gap-1 font-semibold leading-tight"><Crosshair size={10} /><span className="truncate">{focus.ruleId}</span></div>
      <div className="mt-0.5 leading-snug opacity-70">{focus.note}</div>
      {!focus.located && <div className="mt-0.5 leading-snug text-amber-300">Re-run QC after location extraction is available.</div>}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function VerifyFilePage() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const qcResultId = Number(id);
  const returnTo = safeReviewerQueuePath(searchParams.get("returnTo"));

  const [rules, setRules]               = useState<QCRuleResult[]>([]);
  const [loading, setLoading]           = useState(true);
  const [filter, setFilter]             = useState<Filter>("all");
  const [ruleQuery, setRuleQuery]       = useState("");
  const [selectedRuleId, setSelectedRuleId] = useState<number | null>(null);
  const [decisions, setDecisions]       = useState<Record<number, Decision>>({});
  const [comments, setComments]         = useState<Record<number, string>>({});
  const [saving, setSaving]             = useState<number | null>(null);
  const [saved, setSaved]               = useState<Set<number>>(new Set());
  const [progress, setProgress]         = useState<ReviewProgress | null>(null);
  const [documents, setDocuments]       = useState<BatchFile[]>([]);
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null);
  const [pdfError, setPdfError]         = useState(false);
  const [activeFocus, setActiveFocus]   = useState<RuleFocus | null>(null);
  const [activePage, setActivePage]     = useState(1);
  const [pageCount, setPageCount]       = useState<number | null>(null);
  const [viewerWidth, setViewerWidth]   = useState(720);
  const [zoom, setZoom]                 = useState(1);
  const [highlighting, setHighlighting] = useState(false);
  const [submitting, setSubmitting]     = useState(false);
  const [offline, setOffline]           = useState(() => typeof navigator !== "undefined" ? !navigator.onLine : false);
  const [acknowledged, setAcknowledged] = useState<Record<number, boolean>>({});
  const [signoffOpen, setSignoffOpen]   = useState(false);
  const [signoffCode, setSignoffCode]   = useState("");
  const [submitNotes, setSubmitNotes]   = useState("");
  const [saveNotice, setSaveNotice]     = useState<{ text: string; tone: "success" | "error" | "info" } | null>(null);

  const viewerRef = useRef<HTMLDivElement | null>(null);
  const ruleSearchRef = useRef<HTMLInputElement | null>(null);
  const inFlightDecisionIds = useRef<Set<number>>(new Set());
  const commentRefs = useRef<Record<number, HTMLTextAreaElement | null>>({});

  // ── Hooks ────────────────────────────────────────────────────────────────
  const {
    sessionToken, sessionError, sessionAckRequired,
    beginSession, clearError: clearSessionError,
  } = useReviewSession(qcResultId);

  const progressTopic = `/topic/reviewer/qc/${qcResultId}/progress`;
  const decisionTopic = `/topic/reviewer/qc/${qcResultId}/decision`;

  const applySavedDecision = useCallback((ruleId: number, savedDecision: DecisionEvent, fallbackComment?: string) => {
    setDecisions(prev => ({ ...prev, [ruleId]: savedDecision.decision }));
    setSaved(prev => new Set(prev).add(ruleId));
    setRules(prev => prev.map(item => item.id === ruleId ? {
      ...item, status: ruleStatus(savedDecision.status),
      reviewerVerified: savedDecision.reviewerVerified ?? undefined,
      reviewerComment: savedDecision.reviewerComment ?? fallbackComment ?? item.reviewerComment,
      overridePending: Boolean(savedDecision.overridePending),
      verifiedAt: savedDecision.savedAt,
    } : item));
  }, []);

  const { connected: realtimeConnected } = useWebSocket(
    useMemo(() => [progressTopic, decisionTopic], [progressTopic, decisionTopic]),
    useCallback((topic: string, payload: unknown) => {
      if (topic === progressTopic && payload && typeof payload === "object") {
        const next = payload as ReviewProgress;
        setProgress({ pending: Number(next.pending ?? 0), canSubmit: Boolean(next.canSubmit), totalToVerify: Number(next.totalToVerify ?? 0) });
      }
      if (topic === decisionTopic && payload && typeof payload === "object") {
        const next = payload as DecisionEvent;
        if (typeof next.ruleResultId === "number") {
          applySavedDecision(next.ruleResultId, next);
          inFlightDecisionIds.current.delete(next.ruleResultId);
          setSaving(current => current === next.ruleResultId ? null : current);
        }
      }
    }, [progressTopic, decisionTopic, applySavedDecision])
  );

  // ── Data loading ─────────────────────────────────────────────────────────
  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const [rulesData, prog] = await Promise.all([getQCRules(qcResultId), getQCProgress(qcResultId)]);
      setRules(rulesData.map(r => ({ ...r, status: ruleStatus(r.status) })));
      setProgress(prog);
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
    const timer = window.setTimeout(() => { void loadRules(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadRules]);

  useEffect(() => {
    getQCFileInfo(qcResultId)
      .then(d => {
        const docs = d.documents?.length ? d.documents : d.batchFile ? [d.batchFile] : [];
        setDocuments(docs); setActiveDocumentId(d.batchFile?.id ?? docs[0]?.id ?? null);
        setPdfError(docs.length === 0);
      }).catch(() => setPdfError(true));
  }, [qcResultId]);

  useEffect(() => {
    const markOnline = () => setOffline(false);
    const markOffline = () => setOffline(true);
    window.addEventListener("online", markOnline); window.addEventListener("offline", markOffline);
    return () => { window.removeEventListener("online", markOnline); window.removeEventListener("offline", markOffline); };
  }, []);

  useEffect(() => { if (!saveNotice) return; const t = window.setTimeout(() => setSaveNotice(null), 3500); return () => window.clearTimeout(t); }, [saveNotice]);

  useEffect(() => {
    if (!viewerRef.current) return;
    const observer = new ResizeObserver(entries => {
      const width = entries[0]?.contentRect.width;
      if (width) setViewerWidth(Math.max(320, Math.floor(width - 48)));
    });
    observer.observe(viewerRef.current);
    return () => observer.disconnect();
  }, []);

  // ── Derived state ─────────────────────────────────────────────────────────
  const activeDocument = useMemo(
    () => documents.find(doc => doc.id === activeDocumentId) ?? documents[0],
    [documents, activeDocumentId]
  );
  const documentWarnings = useMemo(() => documents.flatMap(doc =>
    (doc.documentQualityFlags ?? "").split("\n").map(f => f.trim()).filter(Boolean)
      .map(f => `${doc.fileType === "ENGAGEMENT" ? "Order" : doc.fileType === "APPRAISAL" ? "Report" : "Contract"}: ${f}`)
  ), [documents]);
  const activeDocumentUrl = activeDocument ? getPdfUrl(activeDocument.id) : undefined;

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
  }).filter(r => {
    const q = ruleQuery.trim().toLowerCase();
    if (!q) return true;
    return [r.ruleId, r.ruleName, r.message, r.verifyQuestion, r.rejectionText, r.appraisalValue, r.engagementValue, r.evidence]
      .some(v => String(v ?? "").toLowerCase().includes(q));
  });

  const reviewedCount  = (progress?.totalToVerify ?? 0) - (progress?.pending ?? 0);
  const reviewProgress = progress?.totalToVerify ? Math.round((reviewedCount / progress.totalToVerify) * 100) : 0;
  const passedDecisions = Object.values(decisions).filter(v => v === "PASS").length;
  const failedDecisions = Object.values(decisions).filter(v => v === "FAIL").length;
  const nextPendingRule = rules.find(r => r.reviewRequired && !decisions[r.id]);
  const activeRule = rules.find(r => r.id === selectedRuleId)
    ?? rules.find(r => r.ruleId === activeFocus?.ruleId)
    ?? nextPendingRule ?? filtered[0];

  const saveTone = saveNotice?.tone === "error"
    ? "border-red-800/50 bg-red-950/50 text-red-200"
    : saveNotice?.tone === "success"
      ? "border-green-800/50 bg-green-950/50 text-green-200"
      : "border-slate-700 bg-slate-900 text-slate-300";

  useEffect(() => {
    if (filtered.length === 0) return;
    if (activeRule && filtered.some(r => r.id === activeRule.id)) return;
    const t = window.setTimeout(() => setSelectedRuleId(filtered[0].id), 0);
    return () => window.clearTimeout(t);
  }, [activeRule, filtered]);

  // ── Actions ───────────────────────────────────────────────────────────────
  function focusRule(rule: QCRuleResult) {
    setSelectedRuleId(rule.id);
    const nextFocus = focusForRule(rule);
    if (!nextFocus.located) { setActiveFocus(nextFocus); setHighlighting(false); return; }
    const preferredDoc = documents.find(doc => doc.fileType === nextFocus.documentType) ?? documents.find(doc => doc.fileType === "APPRAISAL") ?? documents[0];
    if (preferredDoc) setActiveDocumentId(preferredDoc.id);
    setActiveFocus(nextFocus); setActivePage(nextFocus.page); setHighlighting(true);
    window.setTimeout(() => setHighlighting(false), 5000);
  }

  function jumpToNextPending() {
    if (!nextPendingRule) return;
    setFilter("all"); focusRule(nextPendingRule);
    window.setTimeout(() => { document.getElementById(`rule-${nextPendingRule.id}`)?.scrollIntoView({ block: "center", behavior: "smooth" }); }, 50);
  }

  function moveActiveRule(delta: number) {
    if (filtered.length === 0) return;
    const currentIndex = Math.max(0, filtered.findIndex(r => r.id === activeRule?.id));
    const next = filtered[Math.min(Math.max(currentIndex + delta, 0), filtered.length - 1)];
    setSelectedRuleId(next.id); focusRule(next);
    window.setTimeout(() => { document.getElementById(`rule-${next.id}`)?.scrollIntoView({ block: "center", behavior: "smooth" }); }, 0);
  }

  function cycleDocument(delta: number) {
    if (documents.length <= 1) return;
    const currentIndex = Math.max(0, documents.findIndex(doc => doc.id === activeDocument?.id));
    const next = documents[(currentIndex + delta + documents.length) % documents.length];
    setActiveDocumentId(next.id); setPageCount(null); setPdfError(false); setActiveFocus(null); setActivePage(1);
  }

  function keyboardDecisionAllowed(rule: QCRuleResult, decision: Decision): string | null {
    const s = ruleStatus(rule.status);
    if (!rule.reviewRequired) return "This rule does not need a manual decision.";
    if (!sessionToken) return "Review session is not ready yet.";
    if (offline) return "You're offline. Decisions cannot be saved until your connection is restored.";
    if (saving === rule.id) return "This decision is already saving.";
    if (s === "fail" && decision === "PASS" && (comments[rule.id] ?? "").trim().length < 20) return "Add a specific override reason of at least 20 characters before saving Pass.";
    if (s !== "verify" && decision === "FAIL") return "Only Needs Review rules can be saved as Fail.";
    if (s === "verify" && rule.severity === "BLOCKING" && !acknowledged[rule.id]) return "Acknowledge the referenced document sections before saving this blocking rule.";
    return null;
  }

  async function handleDecision(rule: QCRuleResult, decision: Decision) {
    if (inFlightDecisionIds.current.has(rule.id)) return;
    if (!sessionToken) { clearSessionError(); return; }
    if (offline) return;
    const latencyMs = Math.max(0, Date.now() - (rule.firstPresentedAt ? new Date(rule.firstPresentedAt).getTime() : Date.now()));
    inFlightDecisionIds.current.add(rule.id);
    setSaving(rule.id);
    try {
      const savedDecision = await saveDecision(rule.id, decision, comments[rule.id], sessionToken, latencyMs, Boolean(acknowledged[rule.id]));
      applySavedDecision(rule.id, savedDecision, comments[rule.id]);
      setSaveNotice({ text: `${rule.ruleId} saved as ${decision}`, tone: "success" });
      setProgress(prev => {
        if (!prev || decisions[rule.id]) return prev;
        const pending = Math.max(0, prev.pending - 1);
        return { ...prev, pending, canSubmit: pending === 0 && prev.totalToVerify > 0 };
      });
      void getQCProgress(qcResultId).then(setProgress).catch(() => undefined);
    } catch (error) {
      setSaveNotice({ text: `${rule.ruleId} was not saved`, tone: "error" });
      void Promise.all([loadRules(), getQCProgress(qcResultId).then(setProgress)]).catch(() => undefined);
    } finally {
      inFlightDecisionIds.current.delete(rule.id);
      setSaving(null);
    }
  }

  async function handleSubmit() {
    if (!sessionToken) return;
    const freshProgress = await getQCProgress(qcResultId);
    setProgress(freshProgress);
    if (!freshProgress.canSubmit) return;
    setSignoffCode(""); setSubmitNotes(""); setSignoffOpen(true);
  }

  async function performSubmit() {
    if (!sessionToken) return;
    const expected = String(qcResultId).slice(-4);
    if (signoffCode.trim() !== expected) return;
    setSubmitting(true);
    try {
      const response = await fetch(`${JAVA}/api/reviewer/qc/${qcResultId}/submit`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: submitNotes.trim(), sessionToken }),
      });
      if (!response.ok) throw new Error("Review submit failed");
      window.location.href = returnTo;
    } finally { setSubmitting(false); setSignoffOpen(false); }
  }

  // ── Keyboard shortcuts (stable listener, reads refs) ────────────────────
  // Keep mutable state in refs so the keydown handler closure (registered once) can access fresh values
  const kbStateRef = useRef({
    activeRule: undefined as QCRuleResult | undefined,
    acknowledged, comments, decisions, documents, filter, filtered,
    offline, ruleQuery, saving, sessionError, sessionToken,
  });
  kbStateRef.current = { activeRule, acknowledged, comments, decisions, documents, filter, filtered, offline, ruleQuery, saving, sessionError, sessionToken };

  useKeyboardShortcuts(useCallback((event: KeyboardEvent) => {
    const target = event.target as HTMLElement | null;
    const tagName = target?.tagName?.toLowerCase();
    const inTextField = tagName === "input" || tagName === "textarea" || tagName === "select" || Boolean(target?.isContentEditable);
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const kb = kbStateRef.current;

    if (event.key === "Escape") {
      if (kb.ruleQuery) { event.preventDefault(); setRuleQuery(""); ruleSearchRef.current?.blur(); }
      else if (kb.sessionError) { event.preventDefault(); clearSessionError(); }
      return;
    }
    if (!inTextField && event.key.toLowerCase() === "r") {
      event.preventDefault(); void loadRules(); void getQCProgress(qcResultId).then(setProgress).catch(() => undefined); return;
    }
    if (!inTextField && event.key === "/") { event.preventDefault(); ruleSearchRef.current?.focus(); return; }
    if (!inTextField && event.key === "1") { event.preventDefault(); setFilter("all"); setSelectedRuleId(null); return; }
    if (!inTextField && event.key === "2") { event.preventDefault(); setFilter("fail"); setSelectedRuleId(null); return; }
    if (!inTextField && event.key === "3") { event.preventDefault(); setFilter("verify"); setSelectedRuleId(null); return; }
    if (!inTextField && event.key === "4") { event.preventDefault(); setFilter("pass"); setSelectedRuleId(null); return; }
    if (!inTextField && (event.key.toLowerCase() === "j" || event.key === "ArrowDown")) { event.preventDefault(); moveActiveRule(1); return; }
    if (!inTextField && (event.key.toLowerCase() === "k" || event.key === "ArrowUp")) { event.preventDefault(); moveActiveRule(-1); return; }
    if (!inTextField && event.key === "Enter" && kb.activeRule) {
      event.preventDefault(); focusRule(kb.activeRule);
      document.getElementById(`rule-${kb.activeRule.id}`)?.scrollIntoView({ block: "center", behavior: "smooth" }); return;
    }
    if (!inTextField && event.key.toLowerCase() === "n") { event.preventDefault(); jumpToNextPending(); return; }
    if (!inTextField && event.key.toLowerCase() === "c") { event.preventDefault(); if (kb.activeRule) commentRefs.current[kb.activeRule.id]?.focus(); return; }
    if (!inTextField && event.key.toLowerCase() === "a" && kb.activeRule) {
      event.preventDefault(); setAcknowledged(prev => ({ ...prev, [kb.activeRule!.id]: !prev[kb.activeRule!.id] })); return;
    }
    if (!inTextField && event.key.toLowerCase() === "s") { event.preventDefault(); void handleSubmit(); return; }
    if (!inTextField && event.key === "[") { event.preventDefault(); cycleDocument(-1); return; }
    if (!inTextField && event.key === "]") { event.preventDefault(); cycleDocument(1); return; }
    if (!inTextField && (event.key === "+" || event.key === "=")) { event.preventDefault(); setZoom(v => Math.min(1.8, Math.round((v + 0.1) * 10) / 10)); return; }
    if (!inTextField && event.key === "-") { event.preventDefault(); setZoom(v => Math.max(0.6, Math.round((v - 0.1) * 10) / 10)); return; }
    if (!inTextField && event.key === "0") { event.preventDefault(); setZoom(1); return; }
    if (!inTextField && kb.activeRule && (event.key.toLowerCase() === "p" || event.key.toLowerCase() === "f")) {
      const decision: Decision = event.key.toLowerCase() === "p" ? "PASS" : "FAIL";
      const blocked = keyboardDecisionAllowed(kb.activeRule, decision);
      if (blocked) return;
      event.preventDefault(); void handleDecision(kb.activeRule, decision);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []));

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <DeviceGate minWidth={1024} title="Document review needs a laptop or desktop width"
      message="The PDF comparison and rule decision workspace needs side-by-side document and data panels. Please use a laptop, desktop, or a tablet in landscape mode."
      allowTablet={false}>
      <div className="h-screen flex flex-col bg-slate-950 text-white overflow-hidden">
        {activeFocus && <RuleFocusOverlay focus={activeFocus} highlighting={highlighting} />}

        {(offline || sessionError) && (
          <div className={`flex items-center gap-3 px-4 py-2 text-xs border-b ${offline ? "bg-red-950/60 border-red-800/50 text-red-200" : "bg-amber-950/60 border-amber-800/50 text-amber-100"}`}>
            <span className="flex-1">{offline ? "You're offline. Decisions are frozen until the connection is restored." : sessionError}</span>
            {sessionAckRequired && (
              <button onClick={() => void beginSession(true)} className="h-7 rounded-md border border-amber-700/60 bg-amber-900/30 px-2.5 text-[11px] font-semibold text-amber-100 hover:bg-amber-800/40">
                Review prior decisions and continue
              </button>
            )}
          </div>
        )}

        {documentWarnings.length > 0 && (
          <div className="border-b border-red-800/40 bg-red-950/40 px-4 py-2 text-xs text-red-100">
            <div className="font-semibold">Document quality warning</div>
            <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-1">
              {documentWarnings.map((w, i) => <span key={i}>{w}</span>)}
            </div>
          </div>
        )}

        {/* Top bar */}
        <header className="flex-shrink-0 flex items-center gap-3 px-4 h-12 bg-slate-900 border-b border-slate-800">
          <a href={returnTo} className="flex items-center gap-1.5 text-slate-400 hover:text-white text-sm transition-colors flex-shrink-0">
            <ArrowLeft size={14} /> Queue
          </a>
          <div className="w-px h-4 bg-slate-700 flex-shrink-0" />
          <span className="text-sm font-medium text-slate-300 truncate flex-1">QC Result #{qcResultId}</span>
          <div className="hidden sm:flex items-center gap-2 flex-shrink-0">
            <CountBadge label="Pass"         count={counts.pass}   style="text-green-400 bg-green-950/50 border-green-800/50" />
            <CountBadge label="Fail"         count={counts.fail}   style="text-red-400   bg-red-950/50   border-red-800/50" />
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
          <div className={`hidden lg:flex h-8 min-w-[150px] items-center gap-1.5 rounded-md border px-2 text-[11px] ${saveNotice ? saveTone : offline ? "border-red-800/50 bg-red-950/40 text-red-200" : "border-slate-800 bg-slate-950/60 text-slate-400"}`}>
            {offline ? <WifiOff size={12} /> : saveNotice?.tone === "success" ? <CheckCircle2 size={12} /> : <Cloud size={12} />}
            <span className="truncate">{saveNotice?.text ?? (offline ? "Saving paused" : realtimeConnected ? "Live save ready" : "REST save ready")}</span>
          </div>
          {nextPendingRule && (
            <button onClick={jumpToNextPending} aria-keyshortcuts="N"
              className="hidden xl:inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-300 transition-colors hover:bg-slate-800 hover:text-white">
              <ArrowDownCircle size={13} /> Next item
            </button>
          )}
          <button onClick={() => void handleSubmit()} disabled={!progress?.canSubmit || submitting || offline || !sessionToken}
            className="flex-shrink-0 flex items-center gap-1.5 h-8 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-xs font-semibold transition-colors">
            {submitting ? <svg className="animate-spin h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> : null}
            {submitting ? "Submitting…" : progress?.pending ? `Submit (${progress.pending} left)` : "Submit review"}
          </button>
        </header>

        <div className="flex flex-1 overflow-hidden">
          {/* PDF viewer */}
          <div className="w-[55%] flex-shrink-0 border-r border-slate-800 flex flex-col">
            <div className="flex-shrink-0 px-4 py-2 border-b border-slate-800 flex items-center gap-2">
              <svg className="w-3.5 h-3.5 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              <span className="text-xs text-slate-500 flex-shrink-0">Documents</span>
              <div className="flex items-center gap-1 overflow-x-auto">
                {documents.map(doc => (
                  <button key={doc.id} onClick={() => { setActiveDocumentId(doc.id); setPageCount(null); setPdfError(false); setActiveFocus(null); setActivePage(1); }}
                    className={`h-7 px-2 rounded-md text-[11px] font-medium border transition-colors whitespace-nowrap ${activeDocument?.id === doc.id ? "bg-blue-600/20 border-blue-500/50 text-blue-200" : "bg-slate-900 border-slate-800 text-slate-500 hover:text-slate-300"}`}>
                    {doc.fileType === "APPRAISAL" ? "Report" : doc.fileType === "ENGAGEMENT" ? "Order" : doc.fileType === "CONTRACT" ? "Contract" : "PDF"}
                  </button>
                ))}
              </div>
              {activeDocument && (
                <div className="ml-auto flex items-center gap-1 text-[11px] text-slate-500">
                  {pageCount != null && <span className="mr-1 hidden font-mono text-slate-600 lg:inline">{activePage}/{pageCount}</span>}
                  <button onClick={() => setZoom(v => Math.max(0.6, Math.round((v - 0.1) * 10) / 10))} disabled={zoom <= 0.6} className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-slate-800 bg-slate-900 text-slate-400 disabled:opacity-30 hover:text-white" title="Zoom out" aria-keyshortcuts="-"><ZoomOut size={13} /></button>
                  <button onClick={() => setZoom(1)} className="h-7 min-w-12 rounded-md border border-slate-800 bg-slate-900 px-2 font-mono text-slate-400 hover:text-white" title="Reset zoom" aria-keyshortcuts="0">{Math.round(zoom * 100)}%</button>
                  <button onClick={() => setZoom(v => Math.min(1.8, Math.round((v + 0.1) * 10) / 10))} disabled={zoom >= 1.8} className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-slate-800 bg-slate-900 text-slate-400 disabled:opacity-30 hover:text-white" title="Zoom in" aria-keyshortcuts="+"><ZoomIn size={13} /></button>
                </div>
              )}
            </div>
            {activeDocument ? (
              <div ref={viewerRef} className={`relative flex-1 overflow-auto bg-slate-950 ${highlighting ? "ring-2 ring-amber-400 ring-inset" : ""}`}>
                <div className="min-h-full flex justify-center px-4 py-12">
                  <div className="relative">
                    <PdfDocumentViewer key={activeDocument.id} fileUrl={activeDocumentUrl}
                      targetPage={activePage} targetBox={activeFocus?.bbox ?? null}
                      width={Math.round(viewerWidth * zoom)} highlighting={highlighting}
                      onLoadSuccess={numPages => { setPageCount(numPages); setPdfError(false); setActivePage(p => Math.min(Math.max(p, 1), numPages)); }}
                      onLoadError={() => setPdfError(true)} />
                  </div>
                </div>
              </div>
            ) : pdfError ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-500">
                <AlertTriangle size={18} className="text-amber-500" /><span className="text-sm">Document unavailable</span>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <svg className="animate-spin h-6 w-6 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
              </div>
            )}
          </div>

          {/* Rules panel */}
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex-shrink-0 border-b border-slate-800 px-3 py-2">
              <div className="mb-2 flex items-center gap-2">
                <div className="mr-2 hidden min-w-0 flex-1 lg:block">
                  <div className="text-xs font-medium text-slate-300">Decision checklist</div>
                  <div className="text-[11px] text-slate-600">{progress?.pending ? `${progress.pending} server-confirmed decision${progress.pending === 1 ? "" : "s"} left` : "Ready for sign-off"}</div>
                </div>
                <button onClick={jumpToNextPending} disabled={!nextPendingRule}
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-300 transition-colors hover:bg-slate-800 hover:text-white disabled:opacity-40" title="Next pending rule (N)">
                  <ArrowDownCircle size={13} /> Next item
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-1">
                <div className="relative mr-1 min-w-44 flex-1">
                  <Search size={12} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-600" />
                  <input ref={ruleSearchRef} value={ruleQuery} onChange={e => setRuleQuery(e.target.value)}
                    placeholder="Search rules..."
                    className="h-7 w-full rounded-md border border-slate-800 bg-slate-900 pl-7 pr-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500" />
                </div>
                {FILTERS.map(f => (
                  <button key={f} onClick={() => { setFilter(f); setSelectedRuleId(null); }}
                    aria-pressed={filter === f}
                    aria-keyshortcuts={f === "all" ? "1" : f === "fail" ? "2" : f === "verify" ? "3" : "4"}
                    className={`h-7 px-2.5 rounded-md text-xs font-medium transition-colors ${filter === f ? "bg-blue-600 text-white" : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"}`}>
                    {f === "all" ? `All (${counts.total})` : f === "fail" ? `Fail (${counts.fail})` : f === "verify" ? `Needs Review (${counts.review})` : `Pass (${counts.pass})`}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {loading ? <PageSpinner label="Loading rules…" /> : filtered.length === 0 ? (
                <div className="text-center text-slate-500 py-10 text-sm">No rules match this filter</div>
              ) : filtered.map(rule => (
                <RuleCard
                  key={rule.id}
                  rule={rule}
                  decision={decisions[rule.id]}
                  comment={comments[rule.id] ?? ""}
                  saving={saving === rule.id}
                  savedNow={saved.has(rule.id)}
                  offline={offline}
                  sessionReady={Boolean(sessionToken)}
                  acknowledged={Boolean(acknowledged[rule.id])}
                  active={activeRule?.id === rule.id}
                  onSelect={() => focusRule(rule)}
                  onDecision={d => void handleDecision(rule, d)}
                  onAcknowledge={checked => setAcknowledged(prev => ({ ...prev, [rule.id]: checked }))}
                  onComment={c => setComments(prev => ({ ...prev, [rule.id]: c }))}
                  commentRef={node => { commentRefs.current[rule.id] = node; }}
                />
              ))}
            </div>
          </div>
        </div>

        <SignOffDialog
          open={signoffOpen}
          qcResultId={qcResultId}
          totalReviewed={progress?.totalToVerify ?? 0}
          passed={passedDecisions}
          failed={failedDecisions}
          code={signoffCode}
          notes={submitNotes}
          submitting={submitting}
          onCodeChange={setSignoffCode}
          onNotesChange={setSubmitNotes}
          onCancel={() => setSignoffOpen(false)}
          onConfirm={() => void performSubmit()}
        />
      </div>
    </DeviceGate>
  );
}

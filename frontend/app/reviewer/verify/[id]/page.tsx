"use client";
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { useParams, useSearchParams } from "next/navigation";
import {
  ArrowLeft, ChevronDown, ChevronUp, Check, X, AlertTriangle, CheckCircle2,
  Crosshair, ZoomIn, ZoomOut, Save, Cloud, WifiOff, ArrowDownCircle,
  Search,
} from "lucide-react";
import { getQCRules, getQCProgress, saveDecision, getPdfUrl, getQCFileInfo, getRealtimeUrl, startReviewSession, heartbeatReviewSession, type BatchFile, type QCRuleResult } from "@/lib/api";
import { PageSpinner } from "@/components/shared/Spinner";
import DeviceGate from "@/components/shared/DeviceGate";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";
const PdfDocumentViewer = dynamic(() => import("./PdfDocumentViewer"), {
  ssr: false,
  loading: () => <PageSpinner label="Loading document viewer..." />,
});

type Decision = "PASS" | "FAIL";
type Filter = "all" | "fail" | "verify" | "pass";
const FILTERS: Filter[] = ["all", "fail", "verify", "pass"];
type RuleFocus = {
  ruleId: string;
  page: number;
  documentType: string;
  note: string;
  bbox?: { x: number; y: number; w: number; h: number } | null;
  located: boolean;
};
type ReviewProgress = { pending: number; canSubmit: boolean; totalToVerify: number };
type DecisionEvent = {
  ruleResultId: number;
  decision: Decision;
  savedAt: string;
  status: string;
  reviewerVerified?: boolean | null;
  overridePending?: boolean;
  reviewerComment?: string;
};

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
  const normalized = status.toLowerCase();
  return normalized === "manual_pass" ? "MANUAL_PASS" : normalized;
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

function safeReviewerQueuePath(value: string | null) {
  if (!value) return "/reviewer/queue";
  try {
    const decoded = decodeURIComponent(value);
    return decoded.startsWith("/reviewer/queue") ? decoded : "/reviewer/queue";
  } catch {
    return value.startsWith("/reviewer/queue") ? value : "/reviewer/queue";
  }
}

export default function VerifyFilePage() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const qcResultId = Number(id);
  const returnTo = safeReviewerQueuePath(searchParams.get("returnTo"));
  const [rules, setRules]         = useState<QCRuleResult[]>([]);
  const [loading, setLoading]     = useState(true);
  const [filter, setFilter]       = useState<Filter>("all");
  const [ruleQuery, setRuleQuery] = useState("");
  const [selectedRuleId, setSelectedRuleId] = useState<number | null>(null);
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
  const [sessionAckRequired, setSessionAckRequired] = useState(false);
  const [offline, setOffline] = useState(() => typeof navigator !== "undefined" ? !navigator.onLine : false);
  const [acknowledged, setAcknowledged] = useState<Record<number, boolean>>({});
  const [signoffOpen, setSignoffOpen] = useState(false);
  const [signoffCode, setSignoffCode] = useState("");
  const [submitNotes, setSubmitNotes] = useState("");
  const [saveNotice, setSaveNotice] = useState<{ text: string; tone: "success" | "error" | "info" } | null>(null);
  const viewerRef = useRef<HTMLDivElement | null>(null);
  const ruleSearchRef = useRef<HTMLInputElement | null>(null);
  const inFlightDecisionIds = useRef<Set<number>>(new Set());
  const commentRefs = useRef<Record<number, HTMLTextAreaElement | null>>({});

  const applySavedDecision = useCallback((ruleId: number, savedDecision: DecisionEvent, fallbackComment?: string) => {
    setDecisions(prev => ({ ...prev, [ruleId]: savedDecision.decision }));
    setSaved(prev => new Set(prev).add(ruleId));
    setRules(prev => prev.map(item => item.id === ruleId ? {
      ...item,
      status: ruleStatus(savedDecision.status),
      reviewerVerified: savedDecision.reviewerVerified ?? undefined,
      reviewerComment: savedDecision.reviewerComment ?? fallbackComment ?? item.reviewerComment,
      overridePending: Boolean(savedDecision.overridePending),
      verifiedAt: savedDecision.savedAt,
    } : item));
  }, []);

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
    window.addEventListener("online", markOnline);
    window.addEventListener("offline", markOffline);
    return () => {
      window.removeEventListener("online", markOnline);
      window.removeEventListener("offline", markOffline);
    };
  }, []);

  const beginSession = useCallback(async (acknowledgeExistingLock = false) => {
    try {
      const session = await startReviewSession(qcResultId, acknowledgeExistingLock);
      setSessionToken(session.sessionToken);
      setSessionAckRequired(false);
      const priorCount = Number(session.priorActionCount ?? 0);
      setSessionError(
        session.lockAcknowledged || priorCount > 0
          ? `You are continuing a report with ${priorCount} prior saved decision${priorCount === 1 ? "" : "s"}. Review existing decisions before sign-off.`
          : null
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to start review session.";
      setSessionToken(null);
      setSessionError(message);
      setSessionAckRequired(message.includes("previous review session") || message.includes("server-saved decision"));
    }
  }, [qcResultId]);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      beginSession().finally(() => {
        if (cancelled) setSessionToken(null);
      });
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [beginSession]);

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
    if (!saveNotice) return;
    const timer = window.setTimeout(() => setSaveNotice(null), 3500);
    return () => window.clearTimeout(timer);
  }, [saveNotice]);

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
  const documentWarnings = useMemo(() => documents.flatMap(doc =>
    (doc.documentQualityFlags ?? "")
      .split("\n")
      .map(flag => flag.trim())
      .filter(Boolean)
      .map(flag => `${doc.fileType === "ENGAGEMENT" ? "Order" : doc.fileType === "APPRAISAL" ? "Report" : "Contract"}: ${flag}`)
  ), [documents]);
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
    setSelectedRuleId(rule.id);
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
    window.setTimeout(() => setHighlighting(false), 5000);
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
          if (message.topic === decisionTopic && message.payload && typeof message.payload === "object") {
            const next = message.payload as DecisionEvent;
            if (typeof next.ruleResultId === "number") {
              applySavedDecision(next.ruleResultId, next);
              inFlightDecisionIds.current.delete(next.ruleResultId);
              setSaving(current => current === next.ruleResultId ? null : current);
            }
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
  }, [applySavedDecision, loadRules, qcResultId]);

  async function handleDecision(rule: QCRuleResult, decision: Decision) {
    if (inFlightDecisionIds.current.has(rule.id)) {
      return;
    }
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
      setSessionError(error instanceof Error ? error.message : "Decision was not saved. Try again.");
      setSaveNotice({ text: `${rule.ruleId} was not saved`, tone: "error" });
      void Promise.all([loadRules(), getQCProgress(qcResultId).then(setProgress)]).catch(() => undefined);
    }
    finally {
      inFlightDecisionIds.current.delete(rule.id);
      setSaving(null);
    }
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
    setSignoffCode("");
    setSubmitNotes("");
    setSignoffOpen(true);
  }

  async function performSubmit() {
    if (!sessionToken) {
      setSessionError("Review session is not ready yet.");
      return;
    }
    const expected = String(qcResultId).slice(-4);
    if (signoffCode.trim() !== expected) {
      setSessionError("Sign-off cancelled. The confirmation digits did not match.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch(`${JAVA}/api/reviewer/qc/${qcResultId}/submit`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: submitNotes.trim(), sessionToken }),
      });
      if (!response.ok) throw new Error("Review submit failed");
      window.location.href = returnTo;
    } finally {
      setSubmitting(false);
      setSignoffOpen(false);
    }
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
  }).filter(r => {
    const q = ruleQuery.trim().toLowerCase();
    if (!q) return true;
    return [
      r.ruleId,
      r.ruleName,
      r.message,
      r.verifyQuestion,
      r.rejectionText,
      r.appraisalValue,
      r.engagementValue,
      r.evidence,
    ].some(value => String(value ?? "").toLowerCase().includes(q));
  });
  const reviewedCount  = (progress?.totalToVerify ?? 0) - (progress?.pending ?? 0);
  const reviewProgress = progress?.totalToVerify ? Math.round((reviewedCount / progress.totalToVerify) * 100) : 0;
  const passedDecisions = Object.values(decisions).filter(value => value === "PASS").length;
  const failedDecisions = Object.values(decisions).filter(value => value === "FAIL").length;
  const nextPendingRule = rules.find(rule => rule.reviewRequired && !decisions[rule.id]);
  const activeRule = rules.find(rule => rule.id === selectedRuleId)
    ?? rules.find(rule => rule.ruleId === activeFocus?.ruleId)
    ?? nextPendingRule
    ?? filtered[0];
  const saveTone = saveNotice?.tone === "error"
    ? "border-red-800/50 bg-red-950/50 text-red-200"
    : saveNotice?.tone === "success"
      ? "border-green-800/50 bg-green-950/50 text-green-200"
      : "border-slate-700 bg-slate-900 text-slate-300";

  function jumpToNextPending() {
    if (!nextPendingRule) return;
    setFilter("all");
    focusRule(nextPendingRule);
    window.setTimeout(() => {
      document.getElementById(`rule-${nextPendingRule.id}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 50);
  }

  function focusComment(rule?: QCRuleResult) {
    if (!rule) return;
    commentRefs.current[rule.id]?.focus();
  }

  function moveActiveRule(delta: number) {
    if (filtered.length === 0) return;
    const currentIndex = Math.max(0, filtered.findIndex(rule => rule.id === activeRule?.id));
    const nextIndex = Math.min(Math.max(currentIndex + delta, 0), filtered.length - 1);
    const next = filtered[nextIndex];
    setSelectedRuleId(next.id);
    focusRule(next);
    window.setTimeout(() => {
      document.getElementById(`rule-${next.id}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 0);
  }

  function cycleDocument(delta: number) {
    if (documents.length <= 1) return;
    const currentIndex = Math.max(0, documents.findIndex(doc => doc.id === activeDocument?.id));
    const next = documents[(currentIndex + delta + documents.length) % documents.length];
    setActiveDocumentId(next.id);
    setPageCount(null);
    setPdfError(false);
    setActiveFocus(null);
    setActivePage(1);
  }

  function setFilterShortcut(next: Filter) {
    setFilter(next);
    setSelectedRuleId(null);
  }

  useEffect(() => {
    if (filtered.length === 0) return;
    if (activeRule && filtered.some(rule => rule.id === activeRule.id)) return;
    const timer = window.setTimeout(() => setSelectedRuleId(filtered[0].id), 0);
    return () => window.clearTimeout(timer);
  }, [activeRule, filtered]);

  function keyboardDecisionAllowed(rule: QCRuleResult, decision: Decision) {
    const normalizedStatus = ruleStatus(rule.status);
    if (!rule.reviewRequired) return "This rule does not need a manual decision.";
    if (!sessionToken) return "Review session is not ready yet.";
    if (offline) return "You're offline. Decisions cannot be saved until your connection is restored.";
    if (saving === rule.id) return "This decision is already saving.";
    if (normalizedStatus === "fail" && decision === "PASS" && (comments[rule.id] ?? "").trim().length < 20) {
      return "Add a specific override reason of at least 20 characters before saving Pass.";
    }
    if (normalizedStatus !== "verify" && decision === "FAIL") return "Only Needs Review rules can be saved as Fail.";
    if (normalizedStatus === "verify" && rule.severity === "BLOCKING" && !acknowledged[rule.id]) {
      return "Acknowledge the referenced document sections before saving this blocking rule.";
    }
    return null;
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName?.toLowerCase();
      const inTextField = tagName === "input" || tagName === "textarea" || tagName === "select" || target?.isContentEditable;
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      if (event.key === "Escape") {
        if (ruleQuery) {
          event.preventDefault();
          setRuleQuery("");
          ruleSearchRef.current?.blur();
        } else if (sessionError) {
          event.preventDefault();
          setSessionError(null);
        }
        return;
      }
      if (!inTextField && event.key.toLowerCase() === "r") {
        event.preventDefault();
        void loadRules();
        void getQCProgress(qcResultId).then(setProgress).catch(() => undefined);
        return;
      }
      if (!inTextField && event.key === "/") {
        event.preventDefault();
        ruleSearchRef.current?.focus();
        return;
      }
      if (!inTextField && event.key === "1") {
        event.preventDefault();
        setFilterShortcut("all");
        return;
      }
      if (!inTextField && event.key === "2") {
        event.preventDefault();
        setFilterShortcut("fail");
        return;
      }
      if (!inTextField && event.key === "3") {
        event.preventDefault();
        setFilterShortcut("verify");
        return;
      }
      if (!inTextField && event.key === "4") {
        event.preventDefault();
        setFilterShortcut("pass");
        return;
      }
      if (!inTextField && (event.key.toLowerCase() === "j" || event.key === "ArrowDown")) {
        event.preventDefault();
        moveActiveRule(1);
        return;
      }
      if (!inTextField && (event.key.toLowerCase() === "k" || event.key === "ArrowUp")) {
        event.preventDefault();
        moveActiveRule(-1);
        return;
      }
      if (!inTextField && event.key === "Enter" && activeRule) {
        event.preventDefault();
        focusRule(activeRule);
        document.getElementById(`rule-${activeRule.id}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
        return;
      }
      if (!inTextField && event.key.toLowerCase() === "n") {
        event.preventDefault();
        jumpToNextPending();
        return;
      }
      if (!inTextField && event.key.toLowerCase() === "c") {
        event.preventDefault();
        focusComment(activeRule);
        return;
      }
      if (!inTextField && event.key.toLowerCase() === "a" && activeRule) {
        event.preventDefault();
        setAcknowledged(prev => ({ ...prev, [activeRule.id]: !prev[activeRule.id] }));
        return;
      }
      if (!inTextField && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void handleSubmit();
        return;
      }
      if (!inTextField && event.key === "[") {
        event.preventDefault();
        cycleDocument(-1);
        return;
      }
      if (!inTextField && event.key === "]") {
        event.preventDefault();
        cycleDocument(1);
        return;
      }
      if (!inTextField && (event.key === "+" || event.key === "=")) {
        event.preventDefault();
        setZoom(value => Math.min(1.8, Math.round((value + 0.1) * 10) / 10));
        return;
      }
      if (!inTextField && event.key === "-") {
        event.preventDefault();
        setZoom(value => Math.max(0.6, Math.round((value - 0.1) * 10) / 10));
        return;
      }
      if (!inTextField && event.key === "0") {
        event.preventDefault();
        setZoom(1);
        return;
      }
      if (!inTextField && activeRule && (event.key.toLowerCase() === "p" || event.key.toLowerCase() === "f")) {
        const decision: Decision = event.key.toLowerCase() === "p" ? "PASS" : "FAIL";
        const blocked = keyboardDecisionAllowed(activeRule, decision);
        if (blocked) {
          setSessionError(blocked);
          return;
        }
        event.preventDefault();
        void handleDecision(activeRule, decision);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRule, acknowledged, comments, documents, filter, filtered, offline, ruleQuery, saving, sessionError, sessionToken]);

  return (
    <DeviceGate
      minWidth={1024}
      title="Document review needs a laptop or desktop width"
      message="The PDF comparison and rule decision workspace needs side-by-side document and data panels. Please use a laptop, desktop, or a tablet in landscape mode."
      allowTablet={false}
    >
    <div className="h-screen flex flex-col bg-slate-950 text-white overflow-hidden">
      {activeFocus && <RuleFocusOverlay focus={activeFocus} highlighting={highlighting} />}
      {(offline || sessionError) && (
        <div className={`flex items-center gap-3 px-4 py-2 text-xs border-b ${offline ? "bg-red-950/60 border-red-800/50 text-red-200" : "bg-amber-950/60 border-amber-800/50 text-amber-100"}`}>
          <span className="flex-1">{offline ? "You're offline. Decisions are frozen until the connection is restored." : sessionError}</span>
          {sessionAckRequired && (
            <button onClick={() => beginSession(true)} className="h-7 rounded-md border border-amber-700/60 bg-amber-900/30 px-2.5 text-[11px] font-semibold text-amber-100 hover:bg-amber-800/40">
              Review prior decisions and continue
            </button>
          )}
        </div>
      )}
      {documentWarnings.length > 0 && (
        <div className="border-b border-red-800/40 bg-red-950/40 px-4 py-2 text-xs text-red-100">
          <div className="font-semibold">Document quality warning</div>
          <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-1">
            {documentWarnings.map((warning, index) => <span key={index}>{warning}</span>)}
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
        <div className={`hidden lg:flex h-8 min-w-[150px] items-center gap-1.5 rounded-md border px-2 text-[11px] ${saveNotice ? saveTone : offline ? "border-red-800/50 bg-red-950/40 text-red-200" : "border-slate-800 bg-slate-950/60 text-slate-400"}`}>
          {offline ? <WifiOff size={12} /> : saveNotice?.tone === "success" ? <CheckCircle2 size={12} /> : <Cloud size={12} />}
          <span className="truncate">{saveNotice?.text ?? (offline ? "Saving paused" : realtimeConnected ? "Live save ready" : "REST save ready")}</span>
        </div>
        {nextPendingRule && (
          <button
            onClick={jumpToNextPending}
            aria-keyshortcuts="N"
            className="hidden xl:inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-300 transition-colors hover:bg-slate-800 hover:text-white"
          >
            <ArrowDownCircle size={13} />
            Next item
          </button>
        )}
        <button onClick={handleSubmit} disabled={!progress?.canSubmit || submitting || offline || !sessionToken}
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
                {pageCount != null && (
                  <span className="mr-1 hidden font-mono text-slate-600 lg:inline">
                    {activePage}/{pageCount}
                  </span>
                )}
                <button
                  onClick={() => setZoom(value => Math.max(0.6, Math.round((value - 0.1) * 10) / 10))}
                  disabled={zoom <= 0.6}
                  className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-slate-800 bg-slate-900 text-slate-400 disabled:opacity-30 hover:text-white"
                  title="Zoom out"
                  aria-keyshortcuts="-"
                >
                  <ZoomOut size={13} />
                </button>
                <button
                  onClick={() => setZoom(1)}
                  className="h-7 min-w-12 rounded-md border border-slate-800 bg-slate-900 px-2 font-mono text-slate-400 hover:text-white"
                  title="Reset zoom"
                  aria-keyshortcuts="0"
                >
                  {Math.round(zoom * 100)}%
                </button>
                <button
                  onClick={() => setZoom(value => Math.min(1.8, Math.round((value + 0.1) * 10) / 10))}
                  disabled={zoom >= 1.8}
                  className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-slate-800 bg-slate-900 text-slate-400 disabled:opacity-30 hover:text-white"
                  title="Zoom in"
                  aria-keyshortcuts="+"
                >
                  <ZoomIn size={13} />
                </button>
              </div>
            )}
          </div>
          {activeDocument ? (
            <div ref={viewerRef} className={`relative flex-1 overflow-auto bg-slate-950 ${highlighting ? "ring-2 ring-amber-400 ring-inset" : ""}`}>
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
          <div className="flex-shrink-0 border-b border-slate-800 px-3 py-2">
            <div className="mb-2 flex items-center gap-2">
              <div className="mr-2 hidden min-w-0 flex-1 lg:block">
              <div className="text-xs font-medium text-slate-300">Decision checklist</div>
              <div className="text-[11px] text-slate-600">
                {progress?.pending ? `${progress.pending} server-confirmed decision${progress.pending === 1 ? "" : "s"} left` : "Ready for sign-off"}
              </div>
            </div>
              <button
                onClick={jumpToNextPending}
                disabled={!nextPendingRule}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-300 transition-colors hover:bg-slate-800 hover:text-white disabled:opacity-40"
                title="Next pending rule (N)"
              >
                <ArrowDownCircle size={13} />
                Next item
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-1">
              <div className="relative mr-1 min-w-44 flex-1">
                <Search size={12} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-600" />
                <input
                  ref={ruleSearchRef}
                  value={ruleQuery}
                  onChange={e => setRuleQuery(e.target.value)}
                  placeholder="Search rules..."
                  className="h-7 w-full rounded-md border border-slate-800 bg-slate-900 pl-7 pr-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
            {FILTERS.map(f => (
              <button key={f} onClick={() => setFilter(f)}
                aria-pressed={filter === f}
                aria-keyshortcuts={f === "all" ? "1" : f === "fail" ? "2" : f === "verify" ? "3" : "4"}
                className={`h-7 px-2.5 rounded-md text-xs font-medium transition-colors ${
                  filter === f ? "bg-blue-600 text-white" : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
                }`}>
                {f === "all" ? `All (${counts.total})` : f === "fail" ? `Fail (${counts.fail})` : f === "verify" ? `Needs Review (${counts.review})` : `Pass (${counts.pass})`}
              </button>
            ))}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {loading ? <PageSpinner label="Loading rules…" /> : filtered.length === 0 ? (
              <div className="text-center text-slate-500 py-10 text-sm">No rules match this filter</div>
            ) : filtered.map(rule => (
              <RuleCard key={rule.id} rule={rule} decision={decisions[rule.id]} comment={comments[rule.id] ?? ""}
                saving={saving === rule.id} savedNow={saved.has(rule.id)}
                offline={offline} sessionReady={Boolean(sessionToken)}
                acknowledged={Boolean(acknowledged[rule.id])}
                active={activeRule?.id === rule.id}
                onSelect={() => focusRule(rule)}
                onDecision={d => handleDecision(rule, d)}
                onAcknowledge={checked => setAcknowledged(prev => ({ ...prev, [rule.id]: checked }))}
                onComment={c => setComments(prev => ({ ...prev, [rule.id]: c }))}
                commentRef={node => { commentRefs.current[rule.id] = node; }} />
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
        onConfirm={performSubmit}
      />
    </div>
    </DeviceGate>
  );
}

function SignOffDialog({ open, qcResultId, totalReviewed, passed, failed, code, notes, submitting, onCodeChange, onNotesChange, onCancel, onConfirm }: {
  open: boolean;
  qcResultId: number;
  totalReviewed: number;
  passed: number;
  failed: number;
  code: string;
  notes: string;
  submitting: boolean;
  onCodeChange: (value: string) => void;
  onNotesChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const timer = window.setTimeout(() => dialogRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(timer);
      previousFocusRef.current?.focus();
    };
  }, [open]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape" && !submitting) {
      e.preventDefault();
      onCancel();
      return;
    }
    if (e.key !== "Tab") return;
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable || focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  if (!open) return null;
  const expected = String(qcResultId).slice(-4);
  const canConfirm = code.trim() === expected && !submitting;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={submitting ? undefined : onCancel} />
      <div
        ref={dialogRef}
        className="relative w-full max-w-sm rounded-lg border border-slate-700 bg-slate-900 p-5 shadow-2xl focus:outline-none"
        role="dialog"
        aria-modal="true"
        aria-labelledby="signoff-dialog-title"
        aria-describedby="signoff-dialog-description"
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-amber-800 bg-amber-950/60">
            <AlertTriangle size={16} className="text-amber-300" />
          </div>
          <div className="min-w-0">
            <h3 id="signoff-dialog-title" className="text-sm font-semibold text-white">Submit review</h3>
            <p id="signoff-dialog-description" className="mt-1 text-sm leading-relaxed text-slate-400">
              This will sign off QC Result #{qcResultId}. The action cannot be undone.
            </p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2">
          <SignOffStat label="Reviewed" value={totalReviewed} />
          <SignOffStat label="Passed" value={passed} />
          <SignOffStat label="Failed" value={failed} danger={failed > 0} />
        </div>
        <label className="mt-4 block text-xs font-medium text-slate-400">
          Type last 4 digits: <span className="font-mono text-slate-200">{expected}</span>
        </label>
        <input
          value={code}
          onChange={e => onCodeChange(e.target.value)}
          autoFocus
          inputMode="numeric"
          maxLength={4}
          className="mt-1.5 h-10 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 font-mono text-sm tracking-[0.25em] text-white placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
          placeholder="0000"
        />
        <label className="mt-4 block text-xs font-medium text-slate-400">
          Sign-off notes
        </label>
        <textarea
          value={notes}
          onChange={e => onNotesChange(e.target.value)}
          rows={3}
          className="mt-1.5 w-full resize-none rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
          placeholder="Optional summary for the completed review..."
        />
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={submitting}
            className="h-9 rounded-lg bg-slate-800 px-4 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-700 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!canConfirm}
            className="h-9 rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:opacity-40"
          >
            {submitting ? "Submitting..." : "Submit review"}
          </button>
        </div>
      </div>
    </div>
  );
}

function SignOffStat({ label, value, danger }: { label: string; value: number; danger?: boolean }) {
  return (
    <div className={`rounded-lg border px-2.5 py-2 ${danger ? "border-red-900/50 bg-red-950/30 text-red-200" : "border-slate-800 bg-slate-950/50 text-slate-200"}`}>
      <div className="text-base font-semibold tabular-nums">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}

function RuleFocusOverlay({ focus, highlighting }: { focus: RuleFocus; highlighting: boolean }) {
  return (
    <div
      className={`pointer-events-none fixed left-3 top-3 z-50 max-w-[180px] rounded-md border px-2 py-1 text-[10px] shadow-lg transition-colors ${
        highlighting
          ? "bg-amber-300/95 border-amber-100 text-slate-950"
          : "bg-slate-900/95 border-slate-700 text-slate-200 opacity-90"
      }`}
    >
      <div className="flex items-center gap-1 font-semibold leading-tight">
        <Crosshair size={10} />
        <span className="truncate">{focus.ruleId}</span>
      </div>
      <div className="mt-0.5 leading-snug opacity-70">{focus.note}</div>
      {!focus.located && (
        <div className="mt-0.5 leading-snug text-amber-300">Re-run QC after location extraction is available.</div>
      )}
    </div>
  );
}

function CountBadge({ label, count, style }: { label: string; count: number; style: string }) {
  return <span className={`text-[11px] px-2 py-0.5 rounded-md border font-medium ${style}`}>{count} {label}</span>;
}

function EvidenceCompare({ rule, status }: { rule: QCRuleResult; status: string }) {
  const found = rule.appraisalValue ?? rule.extractedValue ?? "";
  const expected = rule.engagementValue ?? rule.expectedValue ?? "";
  const pageLabel = typeof rule.pdfPage === "number" && rule.pdfPage > 0 ? `Page ${rule.pdfPage}` : "Page not located";
  const why = status === "fail"
    ? (rule.rejectionText || rule.message || "The extracted report value does not satisfy this rule.")
    : status === "verify"
      ? (rule.verifyQuestion || rule.message || "This rule needs a reviewer decision.")
      : (rule.message || "The rule evidence is shown for traceability.");

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-2.5">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">Evidence</span>
        <span className="rounded border border-blue-900/50 bg-blue-950/30 px-1.5 py-0.5 text-[10px] text-blue-200">{pageLabel}</span>
        {rule.confidence != null && (
          <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-400">
            Confidence {Math.round(Number(rule.confidence) * 100)}%
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <EvidenceValue title="Found in report" value={found} compareTo={expected} tone="found" />
        <EvidenceValue title="Expected from order" value={expected} compareTo={found} tone="expected" />
      </div>
      <div className="mt-2 rounded-md border border-amber-900/30 bg-amber-950/15 px-2.5 py-2 text-xs leading-relaxed text-amber-200">
        {why}
      </div>
    </div>
  );
}

function EvidenceValue({ title, value, compareTo, tone }: { title: string; value: string; compareTo: string; tone: "found" | "expected" }) {
  const compareTokens = new Set(tokenize(compareTo).map(normalizeToken).filter(Boolean));
  const titleColor = tone === "found" ? "text-slate-500" : "text-blue-500";
  const valueColor = tone === "found" ? "text-slate-300" : "text-blue-300";
  return (
    <div className={`rounded-lg p-2.5 ${tone === "found" ? "bg-slate-800/50" : "border border-blue-800/30 bg-blue-950/30"}`}>
      <div className={`mb-1 text-[10px] font-semibold uppercase tracking-wide ${titleColor}`}>{title}</div>
      <div className={`font-mono text-xs leading-relaxed ${valueColor}`}>
        {value ? tokenize(value).map((token, index) => {
          const normalized = normalizeToken(token);
          const mismatch = Boolean(normalized) && !compareTokens.has(normalized);
          return (
            <span key={`${token}-${index}`} className={mismatch ? "rounded bg-amber-400/20 px-0.5 text-amber-200" : undefined}>
              {token}
            </span>
          );
        }) : <span className="text-slate-600">No value extracted</span>}
      </div>
    </div>
  );
}

function tokenize(value: string) {
  return value.split(/(\s+|[,;:()[\]{}]+)/).filter(token => token.length > 0);
}

function normalizeToken(value: string) {
  return value.trim().toLowerCase().replace(/^[^\w.%-]+|[^\w.%-]+$/g, "");
}

function RuleCard({ rule, decision, comment, saving, savedNow, offline, sessionReady, acknowledged, active, onSelect, onDecision, onAcknowledge, onComment, commentRef }: {
  rule: QCRuleResult; decision?: Decision; comment: string; saving: boolean; savedNow: boolean;
  offline: boolean; sessionReady: boolean; acknowledged: boolean;
  active?: boolean; onSelect: () => void; onDecision: (d: Decision) => void; onAcknowledge: (checked: boolean) => void; onComment: (c: string) => void;
  commentRef: (node: HTMLTextAreaElement | null) => void;
}) {
  const normalizedStatus = ruleStatus(rule.status);
  const [expanded, setExpanded] = useState(normalizedStatus === "fail" || normalizedStatus === "verify");
  const [now, setNow] = useState(0);
  const s = STATUS_STYLE[normalizedStatus] ?? STATUS_STYLE["verify"];
  const sev = rule.severity ?? "STANDARD";
  const isVerify = normalizedStatus === "verify";
  const isFail = normalizedStatus === "fail";
  const isBlockingVerify = isVerify && sev === "BLOCKING";
  const presentedAt = rule.firstPresentedAt ? new Date(rule.firstPresentedAt).getTime() : 0;
  const elapsedMs = presentedAt > 0 && now > 0 ? Math.max(0, now - presentedAt) : 0;
  const waitMs = isVerify && presentedAt > 0 ? Math.max(0, 8000 - elapsedMs) : 0;
  const waitSeconds = Math.ceil(waitMs / 1000);
  const slaMs = rule.reviewRequired ? (4 * 60 * 60 * 1000) - elapsedMs : null;
  const slaExpired = slaMs != null && slaMs <= 0;
  const slaUnderHour = slaMs != null && slaMs > 0 && slaMs <= 60 * 60 * 1000;
  const slaLabel = slaMs == null
    ? null
    : slaExpired
      ? "Needs supervisor attention"
      : `${Math.floor(slaMs / 3_600_000)}h ${Math.floor((slaMs % 3_600_000) / 60_000)}m remaining`;
  const overrideReasonOk = !isFail || comment.trim().length >= 20;
  const canAct = sessionReady && !offline && !saving && waitMs === 0 && (!isBlockingVerify || acknowledged);
  const canPass = canAct && overrideReasonOk;
  const canFail = canAct && isVerify;

  useEffect(() => {
    if (!rule.reviewRequired && !isVerify) return;
    const tick = () => setNow(Date.now());
    const startTimer = window.setTimeout(tick, 0);
    const interval = window.setInterval(tick, 500);
    return () => {
      window.clearTimeout(startTimer);
      window.clearInterval(interval);
    };
  }, [isVerify, rule.reviewRequired]);

  return (
    <div id={`rule-${rule.id}`} className={`rounded-xl border p-3 ${s.border} ${s.bg} ${active ? "ring-1 ring-amber-400/70" : ""}`}>
      <button onClick={() => { setExpanded(!expanded); onSelect(); }} className="w-full text-left">
        <div className="flex items-start gap-2">
          <span className="font-mono text-[10px] bg-slate-800/60 border border-slate-700/40 px-1.5 py-0.5 rounded text-slate-400 flex-shrink-0 mt-0.5">{rule.ruleId}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs font-medium text-slate-200">{rule.ruleName}</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${SEV_STYLE[sev] ?? SEV_STYLE.STANDARD}`}>{sev}</span>
              {saving && <span className="text-[10px] text-blue-300 flex items-center gap-0.5"><Save size={9} />saving</span>}
              {!saving && savedNow && <span className="text-[10px] text-teal-400 flex items-center gap-0.5"><CheckCircle2 size={9} />saved</span>}
              {!saving && decision && !savedNow && <span className="text-[10px] text-teal-400 flex items-center gap-0.5"><CheckCircle2 size={9} />saved earlier</span>}
              {rule.overridePending && <span className="text-[10px] text-blue-300 border border-blue-800/50 bg-blue-950/40 rounded px-1.5 py-0.5">second approval pending</span>}
              {slaLabel && (
                <span className={`text-[10px] rounded border px-1.5 py-0.5 ${
                  slaExpired
                    ? "border-red-700/60 bg-red-950/50 text-red-200"
                    : slaUnderHour
                      ? "border-amber-700/50 bg-amber-950/40 text-amber-200"
                      : "border-slate-700/50 bg-slate-900/60 text-slate-400"
                }`}>
                  {slaLabel}
                </span>
              )}
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
          {(rule.appraisalValue || rule.engagementValue || rule.extractedValue || rule.expectedValue) && (
            <EvidenceCompare rule={rule} status={normalizedStatus} />
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
                  {saving ? <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> : <Check size={12} />} Save Pass
                </button>
                {normalizedStatus === "verify" && (
                  <button onClick={() => onDecision("FAIL")} disabled={!canFail}
                    className={`flex-1 flex items-center justify-center gap-1.5 h-8 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 ${decision === "FAIL" ? "bg-red-600 text-white" : "bg-slate-800 hover:bg-red-900/40 hover:text-red-300 text-slate-400 border border-slate-700"}`}>
                    {saving ? <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> : <X size={12} />} Save Fail
                  </button>
                )}
              </div>
              <textarea ref={commentRef} value={comment} onChange={e => onComment(e.target.value)}
                placeholder={isFail ? "Reason for override - be specific (minimum 20 characters)." : "Add a comment (optional)..."} rows={2}
                className="w-full bg-slate-800/50 border border-slate-700/40 rounded-lg px-2.5 py-2 text-xs text-slate-300 placeholder-slate-600 resize-none focus:outline-none focus:ring-1 focus:ring-blue-600/50 transition-colors" />
              {decision && (
                <div className="text-[10px] text-slate-600">
                  Comments are stored when you press Save Pass or Save Fail.
                </div>
              )}
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

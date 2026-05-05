"use client";
import { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { ArrowLeft, ArrowRight, Check, CircleHelp, CornerDownRight, Keyboard, Route, X } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────
export type TooltipStep = {
  target: string;      // CSS selector of element to highlight
  title:  string;
  body:   string;
  position?: "top" | "bottom" | "left" | "right";
  eyebrow?: string;
  flow?: string[];
  shortcut?: string;
  note?: string;
  fallbackTarget?: string;
};

type GuideState = {
  active:     boolean;
  stepIndex:  number;
  tourId:     string;
  steps:      TooltipStep[];
  start:  (id: string, steps: TooltipStep[], options?: { force?: boolean }) => void;
  next:   () => void;
  prev:   () => void;
  finish: () => void;
};

const GuideCtx = createContext<GuideState | null>(null);

const STORAGE_KEY = "apprisal_guide_completed";

// ── Provider ─────────────────────────────────────────────────────────────────
export function GuideProvider({ children }: { children: React.ReactNode }) {
  const [active,    setActive]    = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [tourId,    setTourId]    = useState("");
  const [steps,     setSteps]     = useState<TooltipStep[]>([]);

  const isCompleted = useCallback((id: string) => {
    try {
      const done = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as string[];
      return done.includes(id);
    } catch { return false; }
  }, []);

  const markCompleted = useCallback((id: string) => {
    try {
      const done = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as string[];
      if (!done.includes(id)) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify([...done, id]));
      }
    } catch {}
  }, []);

  const start = useCallback((id: string, s: TooltipStep[], options?: { force?: boolean }) => {
    if (!options?.force && isCompleted(id)) return;   // already seen — don't auto-show
    setTourId(id); setSteps(s); setStepIndex(0); setActive(true);
  }, [isCompleted]);

  const finish = useCallback(() => {
    setActive(false);
    if (tourId) markCompleted(tourId);
  }, [tourId, markCompleted]);

  const next = useCallback(() => {
    setStepIndex(i => {
      if (i >= steps.length - 1) { finish(); return i; }
      return i + 1;
    });
  }, [steps.length, finish]);

  const prev = useCallback(() => setStepIndex(i => Math.max(0, i - 1)), []);

  return (
    <GuideCtx.Provider value={{ active, stepIndex, tourId, steps, start, next, prev, finish }}>
      {children}
      {active && <TooltipOverlay />}
    </GuideCtx.Provider>
  );
}

export const useGuide = () => {
  const ctx = useContext(GuideCtx);
  if (!ctx) throw new Error("useGuide must be used inside GuideProvider");
  return ctx;
};

export function GuideButton({
  tourId,
  steps,
  label = "Guide",
  compact = false,
}: {
  tourId: string;
  steps: TooltipStep[];
  label?: string;
  compact?: boolean;
}) {
  const { start } = useGuide();

  return (
    <button
      data-guide="guide-launcher"
      type="button"
      onClick={() => start(tourId, steps, { force: true })}
      className={`inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-white/10 bg-[#161B22]/70 text-sm font-medium text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-slate-100 ${
        compact ? "w-8 px-0" : "px-2.5"
      }`}
      title="Open guided tour"
    >
      <CircleHelp size={14} />
      {!compact && <span>{label}</span>}
    </button>
  );
}

// ── Overlay & tooltip ────────────────────────────────────────────────────────
function TooltipOverlay() {
  const { steps, stepIndex, next, prev, finish } = useContext(GuideCtx)!;
  const step = steps[stepIndex];
  const [pos, setPos] = useState({ top: 200, left: 200, w: 0, h: 0, found: false });
  const tooltipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!step) return;
    const findTarget = () => document.querySelector(step.target) ?? (step.fallbackTarget ? document.querySelector(step.fallbackTarget) : null);
    const syncPosition = () => {
      const el = findTarget();
      if (el) {
        const r = el.getBoundingClientRect();
        setPos({ top: r.top, left: r.left, w: r.width, h: r.height, found: true });
      } else {
        setPos(p => ({ ...p, found: false }));
      }
    };

    const frame = window.requestAnimationFrame(() => {
      const el = findTarget();
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      syncPosition();
    });
    const settle = window.setTimeout(syncPosition, 360);
    window.addEventListener("resize", syncPosition);
    window.addEventListener("scroll", syncPosition, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(settle);
      window.removeEventListener("resize", syncPosition);
      window.removeEventListener("scroll", syncPosition, true);
    };
  }, [step]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") finish();
      if (event.key === "ArrowRight" || event.key === "Enter") {
        event.preventDefault();
        next();
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        prev();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [finish, next, prev]);

  if (!step) return null;

  const direction = step.position ?? "bottom";
  const GAP = 14;
  let tipTop  = pos.top + pos.h + GAP;
  let tipLeft = pos.left;

  if (direction === "top")   { tipTop  = pos.top - GAP - 290; }
  if (direction === "right") { tipLeft = pos.left + pos.w + GAP; tipTop = pos.top; }
  if (direction === "left")  { tipLeft = pos.left - GAP - 360; tipTop = pos.top; }

  return (
    <>
      {/* Dim overlay */}
      <div className="fixed inset-0 z-[80] bg-black/62 pointer-events-none" />

      {/* Highlight ring around target */}
      {pos.found && (
        <div className="fixed z-[90] rounded-lg ring-2 ring-slate-300/90 ring-offset-2 ring-offset-[#05070a] pointer-events-none transition-all shadow-[0_0_34px_rgba(226,232,240,0.18)]"
             style={{ top: pos.top - 5, left: pos.left - 5, width: pos.w + 10, height: pos.h + 10 }} />
      )}

      {/* Tooltip card */}
      <div ref={tooltipRef}
           className="foundation-fade-in fixed z-[100] w-[21rem] max-w-[calc(100vw-1rem)] rounded-lg border border-slate-500/30 bg-[#0B0F14] p-4 shadow-[0_24px_70px_rgba(0,0,0,0.55)]"
           style={{
             top: Math.max(8, Math.min(tipTop, window.innerHeight - 340)),
             left: Math.max(8, Math.min(tipLeft, window.innerWidth - 352)),
           }}>
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
              <Route size={11} />
              <span>{step.eyebrow ?? "Workflow guide"}</span>
            </div>
            <span className="mt-1 block text-xs font-medium text-slate-500">Step {stepIndex + 1} of {steps.length}</span>
          </div>
          <button onClick={finish} className="rounded-md p-1 text-slate-500 hover:bg-white/[0.04] hover:text-slate-300" title="Close guide">
            <X size={14} />
          </button>
        </div>
        <h3 className="mb-1 text-sm font-semibold text-white">{step.title}</h3>
        <p className="mb-3 text-xs leading-relaxed text-slate-400">{step.body}</p>

        {step.flow && step.flow.length > 0 && (
          <div className="mb-3 rounded-md border border-white/10 bg-[#11161C]/80 p-3">
            <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              <CornerDownRight size={11} />
              Operator flow
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {step.flow.map((item, i) => (
                <div key={`${item}-${i}`} className="flex items-center gap-1.5">
                  <span className="rounded border border-white/10 bg-[#0B0F14] px-1.5 py-0.5 text-[10px] font-medium text-slate-300">{item}</span>
                  {i < step.flow!.length - 1 && <ArrowRight size={11} className="text-slate-600" />}
                </div>
              ))}
            </div>
          </div>
        )}

        {step.shortcut && (
          <div className="mb-3 flex items-start gap-2 rounded-md border border-white/10 bg-[#11161C]/60 px-3 py-2 text-[11px] text-slate-400">
            <Keyboard size={13} className="mt-0.5 shrink-0 text-slate-500" />
            <span>{step.shortcut}</span>
          </div>
        )}

        {step.note && (
          <p className="mb-3 rounded-md border border-amber-500/20 bg-amber-950/20 px-3 py-2 text-[11px] leading-relaxed text-amber-100/80">{step.note}</p>
        )}

        {!pos.found && (
          <p className="mb-3 rounded-md border border-white/10 bg-[#11161C]/70 px-3 py-2 text-[11px] text-slate-500">
            This area is not visible on the current screen. Continue the guide or open the matching page from navigation.
          </p>
        )}

        {/* Progress dots */}
        <div className="flex items-center gap-1 mb-4">
          {steps.map((_, i) => (
            <div key={i} className={`h-1.5 rounded-full transition-all ${i === stepIndex ? "w-4 bg-slate-500" : "w-1.5 bg-white/15"}`} />
          ))}
        </div>

        <div className="flex gap-2">
          {stepIndex > 0 && (
            <button onClick={prev}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-md border border-white/10 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/[0.04]">
              <ArrowLeft size={12} /> Back
            </button>
          )}
          <button onClick={next}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-slate-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-slate-500">
            {stepIndex === steps.length - 1 ? <>Done <Check size={12} /></> : <>Next <ArrowRight size={12} /></>}
          </button>
        </div>

        <button onClick={finish} className="w-full mt-2 text-xs text-slate-600 hover:text-slate-400">
          Skip guide
        </button>
      </div>
    </>
  );
}

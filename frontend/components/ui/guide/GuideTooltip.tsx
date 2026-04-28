"use client";
import { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────
export type TooltipStep = {
  target: string;      // CSS selector of element to highlight
  title:  string;
  body:   string;
  position?: "top" | "bottom" | "left" | "right";
};

type GuideState = {
  active:     boolean;
  stepIndex:  number;
  tourId:     string;
  steps:      TooltipStep[];
  start:  (id: string, steps: TooltipStep[]) => void;
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

  const start = useCallback((id: string, s: TooltipStep[]) => {
    if (isCompleted(id)) return;   // already seen — don't re-show
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

// ── Overlay & tooltip ────────────────────────────────────────────────────────
function TooltipOverlay() {
  const { steps, stepIndex, next, prev, finish } = useContext(GuideCtx)!;
  const step = steps[stepIndex];
  const [pos, setPos] = useState({ top: 200, left: 200, w: 0, h: 0, found: false });
  const tooltipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!step) return;
    const el = document.querySelector(step.target);
    if (el) {
      const r = el.getBoundingClientRect();
      setPos({ top: r.top + window.scrollY, left: r.left + window.scrollX, w: r.width, h: r.height, found: true });
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      setPos(p => ({ ...p, found: false }));
    }
  }, [step]);

  if (!step) return null;

  const direction = step.position ?? "bottom";
  const GAP = 12;
  let tipTop  = pos.top + pos.h + GAP;
  let tipLeft = pos.left;

  if (direction === "top")   { tipTop  = pos.top - GAP - 240; }
  if (direction === "right") { tipLeft = pos.left + pos.w + GAP; tipTop = pos.top; }
  if (direction === "left")  { tipLeft = pos.left - GAP - 280; tipTop = pos.top; }

  return (
    <>
      {/* Dim overlay */}
      <div className="fixed inset-0 bg-black/50 z-40 pointer-events-none" />

      {/* Highlight ring around target */}
      {pos.found && (
        <div className="fixed z-41 rounded-lg ring-2 ring-blue-400 ring-offset-2 pointer-events-none transition-all"
             style={{ top: pos.top - 4, left: pos.left - 4, width: pos.w + 8, height: pos.h + 8 }} />
      )}

      {/* Tooltip card */}
      <div ref={tooltipRef}
           className="fixed z-50 w-72 bg-slate-900 border border-blue-600 rounded-2xl shadow-2xl p-5"
           style={{ top: Math.max(8, tipTop), left: Math.max(8, Math.min(tipLeft, window.innerWidth - 300)) }}>
        <div className="flex justify-between items-start mb-2">
          <span className="text-xs text-blue-400 font-medium">Step {stepIndex + 1} of {steps.length}</span>
          <button onClick={finish} className="text-slate-500 hover:text-slate-300 text-sm">✕</button>
        </div>
        <h3 className="font-semibold text-white text-sm mb-1">{step.title}</h3>
        <p className="text-slate-400 text-xs leading-relaxed mb-4">{step.body}</p>

        {/* Progress dots */}
        <div className="flex items-center gap-1 mb-4">
          {steps.map((_, i) => (
            <div key={i} className={`h-1.5 rounded-full transition-all ${i === stepIndex ? "bg-blue-500 w-4" : "bg-slate-700 w-1.5"}`} />
          ))}
        </div>

        <div className="flex gap-2">
          {stepIndex > 0 && (
            <button onClick={prev}
              className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg text-xs font-medium">
              ← Back
            </button>
          )}
          <button onClick={next}
            className="flex-1 bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded-lg text-xs font-medium">
            {stepIndex === steps.length - 1 ? "Done ✓" : "Next →"}
          </button>
        </div>

        <button onClick={finish} className="w-full mt-2 text-xs text-slate-600 hover:text-slate-400">
          Skip guide
        </button>
      </div>
    </>
  );
}

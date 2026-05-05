"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrainCircuit, FileCheck2, HelpCircle, Inbox, LogOut } from "lucide-react";
import type { ComponentType } from "react";
import { logout } from "@/lib/api";
import ToastContainer from "./Toast";
import DeviceGate from "./DeviceGate";
import { GuideButton, type TooltipStep } from "@/components/ui/guide/GuideTooltip";

const REVIEWER_QUEUE_GUIDE_STEPS: TooltipStep[] = [
  {
    target: '[data-guide="reviewer-nav"]',
    eyebrow: "Reviewer desk",
    title: "Stay inside the assigned workflow",
    body: "Queue is the reviewer home. Help stays available for status explanations while active reviews keep a clear badge in the top bar.",
    position: "bottom",
    flow: ["Queue", "Verify", "Sign off", "Return"],
  },
  {
    target: '[data-guide="reviewer-queue-next"]',
    fallbackTarget: '[data-guide="reviewer-workspace"]',
    eyebrow: "Prioritization",
    title: "Start with the highest-risk file",
    body: "The queue sorts failures first, then files with more VERIFY items, then older work. The next action card opens the highest priority result.",
    position: "top",
    flow: ["Failures", "More VERIFY", "Oldest first"],
    shortcut: "Press N to open the next prioritized item.",
  },
  {
    target: '[data-guide="reviewer-queue-filters"]',
    fallbackTarget: '[data-guide="reviewer-workspace"]',
    eyebrow: "Queue control",
    title: "Filter without losing your place",
    body: "Search by filename, QC id, or decision. Use All, Failures, and Review-only views to narrow assigned work.",
    position: "bottom",
    shortcut: "/ focuses search, 1 shows all, 2 shows failures, 3 shows review-only, R refreshes.",
  },
  {
    target: '[data-guide="reviewer-queue-list"]',
    fallbackTarget: '[data-guide="reviewer-workspace"]',
    eyebrow: "Open review",
    title: "Choose a file and enter verification",
    body: "Opening a queue item navigates to the verification workspace with a return path back to your filtered queue.",
    position: "top",
    flow: ["Select row", "Review", "Session starts"],
  },
  {
    target: '[data-guide="guide-launcher"]',
    eyebrow: "Help system",
    title: "Open this guide anytime",
    body: "The reviewer guide changes between queue and active verification so it always explains the page you are using.",
    position: "left",
  },
];

const REVIEWER_VERIFY_GUIDE_STEPS: TooltipStep[] = [
  {
    target: '[data-guide="review-topbar"]',
    eyebrow: "Review session",
    title: "Confirm the session and progress",
    body: "The verify page starts a backend review lock. The command bar shows progress, save state, live connection, focus mode, and final submit controls.",
    position: "bottom",
    flow: ["Start lock", "Load progress", "Save decisions", "Submit"],
  },
  {
    target: '[data-guide="review-document"]',
    eyebrow: "Evidence pane",
    title: "Inspect source documents before deciding",
    body: "Use the PDF side to inspect the appraisal, order, and contract. Rule focus can jump to the extracted page and highlight area.",
    position: "right",
    flow: ["Report", "Order", "Contract", "Highlighted evidence"],
    shortcut: "[ and ] switch documents, + and - zoom, 0 resets zoom.",
  },
  {
    target: '[data-guide="review-rules"]',
    eyebrow: "Decision checklist",
    title: "Save auditable PASS/FAIL decisions",
    body: "Rules needing review are saved here. VERIFY can pass or fail. Failed rules can be overridden with PASS only with a strong comment, and blocking VERIFY items require acknowledgement.",
    position: "left",
    flow: ["Focus rule", "Compare evidence", "Comment", "Save decision"],
    shortcut: "N jumps to next pending rule, C focuses comment, A toggles acknowledgement, P saves pass, F saves fail.",
    note: "Submit stays locked until all required decisions are saved and the backend says canSubmit is true.",
  },
  {
    target: '[data-guide="review-focus"]',
    eyebrow: "Focus mode",
    title: "Use full-screen review when needed",
    body: "Focus mode hides outer navigation and can enter browser fullscreen for uninterrupted review work. It is optional; the reviewer can stay in the normal shell if they prefer.",
    position: "bottom",
    shortcut: "Use the Focus button to enter or exit. Escape exits browser fullscreen.",
  },
];

export default function ReviewerLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [signingOut, setSigning] = useState(false);
  const guideSteps = pathname.startsWith("/reviewer/verify") ? REVIEWER_VERIFY_GUIDE_STEPS : REVIEWER_QUEUE_GUIDE_STEPS;
  const guideId = pathname.startsWith("/reviewer/verify") ? "reviewer-verify" : "reviewer-shell";

  async function handleSignOut() {
    setSigning(true);
    await logout();
    window.location.href = "/login";
  }

  return (
    <DeviceGate
      minWidth={768}
      title="Reviewer workspace is not available on phones"
      message="The review queue supports tablet and desktop screens. Phone screens are blocked so document decisions do not become cramped or error-prone."
      allowTablet
    >
    <div className="foundation-grid min-h-screen bg-slate-950 text-white flex flex-col">
      {/* Top nav */}
      <header
        data-reviewer-shell-header="true"
        className="sticky top-0 z-30 h-16 flex-shrink-0 border-b border-white/10 bg-[#11161C]/95 backdrop-blur flex items-center px-5 gap-4 shadow-[0_12px_32px_rgba(0,0,0,0.18)]"
      >
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg border border-slate-500/25 bg-slate-600 flex items-center justify-center shadow-[0_0_22px_rgba(226,232,240,0.2)]">
            <span className="text-[11px] font-bold">A</span>
          </div>
          <div className="hidden sm:block">
            <span className="block text-sm font-semibold leading-tight text-white">Ardur QC</span>
            <span className="text-[10px] uppercase tracking-[0.18em] text-slate-600">Reviewer desk</span>
          </div>
        </div>

        <div className="w-px h-5 bg-white/10" />

        <nav data-guide="reviewer-nav" className="flex items-center gap-1">
          <ReviewerNavLink href="/reviewer/queue" active={pathname.startsWith("/reviewer/queue")} icon={Inbox} label="Queue" />
          {pathname.startsWith("/reviewer/verify") && (
            <span className="hidden sm:inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-500/25 bg-slate-950/30 px-2.5 text-sm font-medium text-slate-200">
              <FileCheck2 size={14} />
              Active review
            </span>
          )}
          <ReviewerNavLink href="/help" active={pathname === "/help"} icon={HelpCircle} label="Help" />
        </nav>

        <div className="hidden min-w-0 items-center gap-2 rounded-md border border-white/10 bg-[#161B22]/70 px-2.5 py-1.5 text-[11px] text-slate-500 lg:flex">
          <BrainCircuit size={13} className="shrink-0 text-slate-300" />
          <span className="truncate">Verify evidence. Save decisions. Sign off with traceability.</span>
        </div>

        <div className="ml-auto flex items-center gap-3">
          <GuideButton tourId={guideId} steps={guideSteps} />
          <span className="text-[10px] bg-[#161B22] border border-white/10 text-slate-500 px-2 py-0.5 rounded font-mono uppercase tracking-wide">
            Reviewer
          </span>
          <button
            onClick={handleSignOut}
            disabled={signingOut}
            data-guide="reviewer-signout"
            className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-slate-600 hover:bg-white/[0.04] hover:text-slate-300 transition-colors disabled:opacity-60"
          >
            <LogOut size={14} />
            {signingOut ? "…" : "Sign out"}
          </button>
        </div>
      </header>

      <div
        data-reviewer-shell-content="true"
        data-guide="reviewer-workspace"
        className="flex-1 overflow-auto bg-[radial-gradient(circle_at_top_right,rgba(226,232,240,0.032),transparent_28%)]"
      >
        {children}
      </div>

      <ToastContainer />
    </div>
    </DeviceGate>
  );
}

function ReviewerNavLink({ href, active, icon: Icon, label }: {
  href: string;
  active: boolean;
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
}) {
  return (
    <Link
      href={href}
      className={`flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm transition-colors ${
        active ? "border border-slate-500/20 bg-slate-600/15 text-slate-200 font-medium" : "text-slate-500 hover:bg-white/[0.04] hover:text-slate-200"
      }`}
    >
      <Icon size={14} />
      {label}
    </Link>
  );
}

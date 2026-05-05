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
    title: "Reviewer navigation",
    body: "Queue shows assigned work. Help stays available for operator guidance and status explanations.",
    position: "bottom",
  },
  {
    target: '[data-guide="reviewer-workspace"]',
    title: "Reviewer workspace",
    body: "This area contains your queue or active review screen. Start from the highest-priority assigned file.",
    position: "top",
  },
  {
    target: '[data-guide="guide-launcher"]',
    title: "Open this guide anytime",
    body: "Use this guide button whenever you want the walkthrough again.",
    position: "left",
  },
];

const REVIEWER_VERIFY_GUIDE_STEPS: TooltipStep[] = [
  {
    target: '[data-guide="review-topbar"]',
    title: "Review command bar",
    body: "This bar shows review progress, save state, focus mode, and final submit controls.",
    position: "bottom",
  },
  {
    target: '[data-guide="review-document"]',
    title: "Document evidence",
    body: "Use the PDF side to inspect the appraisal, order, and contract. Rule focus can jump to the extracted page and highlight area.",
    position: "right",
  },
  {
    target: '[data-guide="review-rules"]',
    title: "Decision checklist",
    body: "Rules needing review are saved here. Use comments for overrides and submit only after required decisions are complete.",
    position: "left",
  },
  {
    target: '[data-guide="review-focus"]',
    title: "Focus mode",
    body: "Focus mode hides outer navigation and can enter browser fullscreen for uninterrupted review work.",
    position: "bottom",
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
          <div className="w-8 h-8 rounded-lg border border-blue-500/25 bg-blue-600 flex items-center justify-center shadow-[0_0_22px_rgba(59,130,246,0.2)]">
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
            <span className="hidden sm:inline-flex h-8 items-center gap-1.5 rounded-md border border-blue-500/25 bg-blue-950/30 px-2.5 text-sm font-medium text-blue-200">
              <FileCheck2 size={14} />
              Active review
            </span>
          )}
          <ReviewerNavLink href="/help" active={pathname === "/help"} icon={HelpCircle} label="Help" />
        </nav>

        <div className="hidden min-w-0 items-center gap-2 rounded-md border border-white/10 bg-[#161B22]/70 px-2.5 py-1.5 text-[11px] text-slate-500 lg:flex">
          <BrainCircuit size={13} className="shrink-0 text-blue-300" />
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
        className="flex-1 overflow-auto bg-[radial-gradient(circle_at_top_right,rgba(59,130,246,0.05),transparent_28%)]"
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
        active ? "border border-blue-500/20 bg-blue-600/15 text-blue-200 font-medium" : "text-slate-500 hover:bg-white/[0.04] hover:text-slate-200"
      }`}
    >
      <Icon size={14} />
      {label}
    </Link>
  );
}

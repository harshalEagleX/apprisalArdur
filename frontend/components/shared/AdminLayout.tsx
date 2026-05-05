"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Package, Users, Building2,
  BarChart2, LogOut, ChevronLeft, BrainCircuit,
} from "lucide-react";
import { logout } from "@/lib/api";
import ToastContainer from "./Toast";
import ActivityMonitor from "./ActivityMonitor";
import DeviceGate from "./DeviceGate";
import { GuideButton, type TooltipStep } from "@/components/ui/guide/GuideTooltip";

const NAV = [
  { href: "/admin",          label: "Overview",   Icon: LayoutDashboard },
  { href: "/admin/batches",  label: "Batches",    Icon: Package },
  { href: "/admin/users",    label: "Users",      Icon: Users },
  { href: "/admin/clients",  label: "Clients",    Icon: Building2 },
  { href: "/analytics",      label: "Analytics",  Icon: BarChart2 },
];

const ADMIN_GUIDE_STEPS: TooltipStep[] = [
  {
    target: '[data-guide="admin-sidebar"]',
    eyebrow: "Admin route map",
    title: "Move through the command surface",
    body: "The admin role owns the full intake workflow: client setup, user access, batch processing, reviewer assignment, recovery, and analytics.",
    position: "right",
    flow: ["Clients", "Users", "Batches", "Reviewers", "Analytics"],
  },
  {
    target: '[data-guide="admin-nav-batches"]',
    eyebrow: "Main admin workflow",
    title: "Batches is the operating center",
    body: "Use Batches to upload ZIP files, run QC with the selected model, watch polling progress, stop processing, assign reviewers, and recover errors.",
    position: "right",
    flow: ["Upload ZIP", "Run QC", "Poll progress", "Assign reviewer", "Complete"],
  },
  {
    target: '[data-guide="admin-main"]',
    eyebrow: "Workspace behavior",
    title: "Act on the next operational state",
    body: "Each admin page is built to reduce guessing: scan status, open the exception, perform the next action, then let the system reload or continue polling.",
    position: "left",
    flow: ["Scan", "Decide", "Act", "Confirm"],
  },
  {
    target: '[data-guide="guide-launcher"]',
    eyebrow: "Help system",
    title: "Open the workflow guide anytime",
    body: "The guide changes by page. On Batches it explains intake and QC; on Users and Clients it explains setup; on Analytics it explains supervisor signals.",
    position: "top",
  },
];

const ADMIN_OVERVIEW_GUIDE_STEPS: TooltipStep[] = [
  {
    target: '[data-guide="admin-overview-header"]',
    eyebrow: "Admin overview",
    title: "Start from the operational home",
    body: "The overview summarizes QC intake, review follow-up, failures, recent activity, and reviewer load.",
    position: "bottom",
    flow: ["Dashboard loads", "Counts calculate", "Next action appears"],
  },
  {
    target: '[data-guide="admin-overview-next-action"]',
    fallbackTarget: '[data-guide="admin-main"]',
    eyebrow: "Decision engine",
    title: "Use the next-best action first",
    body: "The overview prioritizes errors first, then unassigned review work, then running QC. This keeps urgent operational work from being buried.",
    position: "bottom",
    flow: ["Errors", "Awaiting review", "QC running", "Clear"],
  },
  {
    target: '[data-guide="admin-overview-metrics"]',
    fallbackTarget: '[data-guide="admin-main"]',
    eyebrow: "System status",
    title: "Read batch health at a glance",
    body: "These cards expose the lifecycle: uploaded, processing, awaiting review, in review, completed, and error state.",
    position: "top",
  },
  {
    target: '[data-guide="admin-overview-workflow"]',
    fallbackTarget: '[data-guide="admin-main"]',
    eyebrow: "Stage shortcuts",
    title: "Jump directly into a queue state",
    body: "Workflow tiles deep-link into filtered Batches views so admins can move straight to running QC, pending review, in-review work, completed work, or errors.",
    position: "top",
    flow: ["QC running", "Awaiting review", "In review", "Completed", "Errors"],
  },
  {
    target: '[data-guide="admin-overview-reviewers"]',
    fallbackTarget: '[data-guide="admin-main"]',
    eyebrow: "Reviewer load",
    title: "Balance assignments by active work",
    body: "Reviewer workload shows active assignments so review work can be assigned to the best available reviewer.",
    position: "left",
  },
];

const ADMIN_BATCHES_GUIDE_STEPS: TooltipStep[] = [
  {
    target: '[data-guide="admin-batches-actions"]',
    eyebrow: "Batch intake",
    title: "Start intake or recover stuck work",
    body: "Upload creates a new batch from a ZIP. Reconcile checks for batches stuck in QC processing and asks the backend to recover them.",
    position: "bottom",
    flow: ["Upload ZIP", "Validate", "Run QC"],
  },
  {
    target: '[data-guide="admin-batches-summary"]',
    eyebrow: "Batch state",
    title: "Read the page-level queue counts",
    body: "Summary pills show what is on this page: running QC, work needing review, ready/retry items, and completed batches.",
    position: "bottom",
  },
  {
    target: '[data-guide="admin-batches-filters"]',
    eyebrow: "Find work",
    title: "Filter by client, batch id, status, and model",
    body: "Search and status filters update the URL. The model selector is sent when Run QC starts, while progress is polled every two seconds.",
    position: "bottom",
    flow: ["Search/filter", "Choose model", "Run QC", "Poll progress"],
  },
  {
    target: '[data-guide="admin-batches-table"]',
    eyebrow: "Row actions",
    title: "Operate each batch from its row",
    body: "Rows expose Run QC, Retry, Stop, Assign reviewer, Delete, and Recovery. REVIEW_PENDING rows are where reviewer assignment happens.",
    position: "top",
    flow: ["Run/Retry", "Stop", "Assign", "Recover"],
  },
];

const ADMIN_USERS_GUIDE_STEPS: TooltipStep[] = [
  {
    target: '[data-guide="admin-users-header"]',
    eyebrow: "Access control",
    title: "Create admins and reviewers",
    body: "Admins are platform scoped. Reviewers should be attached to a client organisation so assignment recommendations can prefer client fit.",
    position: "bottom",
    flow: ["New user", "Choose role", "Attach client if reviewer", "Save"],
  },
  {
    target: '[data-guide="admin-users-search"]',
    eyebrow: "User lookup",
    title: "Search operators before editing",
    body: "Search checks username, full name, and email locally on the loaded page.",
    position: "bottom",
  },
  {
    target: '[data-guide="admin-users-table"]',
    eyebrow: "User lifecycle",
    title: "Edit or remove access deliberately",
    body: "Edit updates profile, role, and client. Delete opens confirmation so access is removed intentionally.",
    position: "top",
    flow: ["Edit", "Validate", "Save", "Reload"],
  },
];

const ADMIN_CLIENTS_GUIDE_STEPS: TooltipStep[] = [
  {
    target: '[data-guide="admin-clients-header"]',
    eyebrow: "Tenant registry",
    title: "Create client organisations first",
    body: "Clients are the tenant layer for uploads and reviewer assignment. A short client code is used by storage and cleanup workflows.",
    position: "bottom",
    flow: ["New client", "Name", "Code", "Save"],
  },
  {
    target: '[data-guide="admin-clients-search"]',
    eyebrow: "Client lookup",
    title: "Find clients by name, code, or status",
    body: "Use this when the tenant list grows and admins need to confirm whether an organisation already exists.",
    position: "bottom",
  },
  {
    target: '[data-guide="admin-clients-grid"]',
    eyebrow: "Client cards",
    title: "Confirm tenant state before upload",
    body: "Client cards show code, status, and creation date. Uploads should be tied to the correct client before QC begins.",
    position: "top",
  },
];

const ADMIN_ANALYTICS_GUIDE_STEPS: TooltipStep[] = [
  {
    target: '[data-guide="analytics-header"]',
    fallbackTarget: '[data-guide="admin-main"]',
    eyebrow: "Supervisor intelligence",
    title: "Change the reporting window",
    body: "Analytics reloads overview, OCR, model/rules, operator, trend, SLA, and anomaly data when the day range changes.",
    position: "bottom",
    flow: ["7d", "30d", "90d", "Reload metrics"],
  },
  {
    target: '[data-guide="analytics-overview"]',
    fallbackTarget: '[data-guide="admin-main"]',
    eyebrow: "Risk signals",
    title: "Use cards as navigation into work",
    body: "Pending Review and VERIFY Over SLA link back into operational queues so analytics can drive action, not just reporting.",
    position: "bottom",
  },
  {
    target: '[data-guide="analytics-sections"]',
    fallbackTarget: '[data-guide="admin-main"]',
    eyebrow: "Quality review",
    title: "Inspect OCR, compliance, operator, trend, and anomaly signals",
    body: "These sections explain document reading quality, rule pass rates, team throughput, SLA issues, and unusual reviewer behavior.",
    position: "top",
  },
];

function adminGuideFor(pathname: string) {
  if (pathname.startsWith("/admin/batches")) return { id: "admin-batches", steps: ADMIN_BATCHES_GUIDE_STEPS, label: "Batch guide" };
  if (pathname.startsWith("/admin/users")) return { id: "admin-users", steps: ADMIN_USERS_GUIDE_STEPS, label: "User guide" };
  if (pathname.startsWith("/admin/clients")) return { id: "admin-clients", steps: ADMIN_CLIENTS_GUIDE_STEPS, label: "Client guide" };
  if (pathname.startsWith("/analytics")) return { id: "admin-analytics", steps: ADMIN_ANALYTICS_GUIDE_STEPS, label: "Analytics guide" };
  if (pathname === "/admin") return { id: "admin-overview", steps: ADMIN_OVERVIEW_GUIDE_STEPS, label: "Overview guide" };
  return { id: "admin-shell", steps: ADMIN_GUIDE_STEPS, label: "Guide" };
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [narrow, setNarrow]     = useState(false);
  const [signingOut, setSigning] = useState(false);
  const guide = adminGuideFor(pathname);

  useEffect(() => {
    const syncSidebar = () => {
      if (window.innerWidth < 1024) setNarrow(true);
    };
    syncSidebar();
    window.addEventListener("resize", syncSidebar);
    return () => window.removeEventListener("resize", syncSidebar);
  }, []);

  async function handleSignOut() {
    setSigning(true);
    await logout();
    window.location.href = "/login";
  }

  return (
    <DeviceGate
      minWidth={768}
      title="Admin workspace is not available on phones"
      message="Batch management, reviewer assignment, and QC tables need tablet or desktop space. Please use a tablet in landscape, laptop, or desktop."
      allowTablet
    >
    <div className="foundation-grid min-h-screen bg-slate-950 text-white flex">
      {/* Sidebar */}
      <aside
        data-guide="admin-sidebar"
        className={`sticky top-0 h-screen flex-shrink-0 border-r border-white/10 bg-[#11161C]/95 shadow-[12px_0_36px_rgba(0,0,0,0.18)] backdrop-blur flex flex-col transition-all duration-200 ${narrow ? "w-14" : "w-60"}`}
      >

        {/* Logo + collapse toggle */}
        <div className="h-16 flex items-center justify-between px-3 border-b border-white/10">
          {!narrow && (
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-8 h-8 rounded-lg border border-slate-500/25 bg-slate-600 flex-shrink-0 flex items-center justify-center shadow-[0_0_22px_rgba(226,232,240,0.22)]">
                <span className="text-xs font-bold text-white">A</span>
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold leading-tight truncate text-white">Ardur QC</div>
                <div className="text-[10px] text-slate-600 uppercase tracking-[0.18em]">Admin control</div>
              </div>
            </div>
          )}
          {narrow && (
            <div className="w-8 h-8 rounded-lg border border-slate-500/25 bg-slate-600 flex items-center justify-center mx-auto shadow-[0_0_22px_rgba(226,232,240,0.22)]">
              <span className="text-xs font-bold text-white">A</span>
            </div>
          )}
          {!narrow && (
            <button
              onClick={() => setNarrow(true)}
              className="rounded-md p-1 text-slate-600 transition-colors hover:bg-white/[0.04] hover:text-slate-300"
              title="Collapse sidebar"
            >
              <ChevronLeft size={14} />
            </button>
          )}
        </div>

        {/* Expand button when narrow */}
        {narrow && (
          <button
            onClick={() => setNarrow(false)}
            className="mx-auto mt-2 rounded-md p-1 text-slate-600 transition-colors hover:bg-white/[0.04] hover:text-slate-300"
            title="Expand sidebar"
          >
            <ChevronLeft size={14} className="rotate-180" />
          </button>
        )}

        {/* Nav */}
        <nav className="flex-1 p-2 space-y-1 mt-1">
          {!narrow && (
            <div className="mb-2 flex items-center gap-2 rounded-lg border border-white/10 bg-[#161B22]/80 px-3 py-2 text-[11px] leading-relaxed text-slate-500">
              <BrainCircuit size={13} className="shrink-0 text-slate-300" />
              <span>Operational decisions, reviewer load, and QC state.</span>
            </div>
          )}
          {NAV.map(({ href, label, Icon }) => {
            const active = pathname === href || (href !== "/admin" && pathname.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                data-guide={`admin-nav-${label.toLowerCase()}`}
                title={narrow ? label : undefined}
                className={`group relative flex items-center gap-3 px-2.5 py-2 rounded-md text-sm transition-colors ${
                  active
                    ? "bg-slate-600/15 text-slate-200 font-medium"
                    : "text-slate-500 hover:text-slate-200 hover:bg-white/[0.04]"
                }`}
              >
                {active && <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r bg-slate-400" />}
                <Icon size={16} className={`flex-shrink-0 ${active ? "text-slate-300" : "text-slate-600 group-hover:text-slate-300"}`} />
                {!narrow && <span className="truncate">{label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Sign out */}
        <div className="p-2 border-t border-white/10">
          <div className={`mb-2 ${narrow ? "flex justify-center" : ""}`}>
            <GuideButton tourId={guide.id} steps={guide.steps} label={guide.label} compact={narrow} />
          </div>
          <button
            onClick={handleSignOut}
            disabled={signingOut}
            data-guide="admin-signout"
            title={narrow ? "Sign out" : undefined}
            className="flex items-center gap-3 w-full px-2.5 py-2 rounded-md text-sm text-slate-600 hover:text-slate-300 hover:bg-white/[0.04] transition-colors disabled:opacity-60"
          >
            <LogOut size={16} className="flex-shrink-0" />
            {!narrow && <span>{signingOut ? "Signing out…" : "Sign out"}</span>}
          </button>
        </div>
      </aside>

      {/* Main */}
      <main
        data-guide="admin-main"
        className="min-w-0 flex-1 overflow-auto bg-[radial-gradient(circle_at_top_right,rgba(226,232,240,0.032),transparent_28%)]"
      >
        <div className="min-h-full">
          {children}
        </div>
      </main>

      {/* Global notifications */}
      <ToastContainer />
      <ActivityMonitor />
    </div>
    </DeviceGate>
  );
}

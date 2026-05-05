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
    title: "Admin navigation",
    body: "Use this sidebar to move between operational areas: overview, batches, users, clients, and analytics.",
    position: "right",
  },
  {
    target: '[data-guide="admin-nav-batches"]',
    title: "Batch operations",
    body: "Batches is where admins upload ZIP files, run QC, assign reviewers, recover errors, and manage processing state.",
    position: "right",
  },
  {
    target: '[data-guide="admin-main"]',
    title: "Primary workspace",
    body: "The main panel changes by page. It is designed for scanning status, acting on exceptions, and keeping QC work moving.",
    position: "left",
  },
  {
    target: '[data-guide="guide-launcher"]',
    title: "Open this guide anytime",
    body: "This button restarts the tour whenever you need it. It is not a one-time-only tooltip anymore.",
    position: "top",
  },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [narrow, setNarrow]     = useState(false);
  const [signingOut, setSigning] = useState(false);

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
              <div className="w-8 h-8 rounded-lg border border-blue-500/25 bg-blue-600 flex-shrink-0 flex items-center justify-center shadow-[0_0_22px_rgba(59,130,246,0.22)]">
                <span className="text-xs font-bold text-white">A</span>
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold leading-tight truncate text-white">Ardur QC</div>
                <div className="text-[10px] text-slate-600 uppercase tracking-[0.18em]">Admin control</div>
              </div>
            </div>
          )}
          {narrow && (
            <div className="w-8 h-8 rounded-lg border border-blue-500/25 bg-blue-600 flex items-center justify-center mx-auto shadow-[0_0_22px_rgba(59,130,246,0.22)]">
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
              <BrainCircuit size={13} className="shrink-0 text-blue-300" />
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
                    ? "bg-blue-600/15 text-blue-200 font-medium"
                    : "text-slate-500 hover:text-slate-200 hover:bg-white/[0.04]"
                }`}
              >
                {active && <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r bg-blue-400" />}
                <Icon size={16} className={`flex-shrink-0 ${active ? "text-blue-300" : "text-slate-600 group-hover:text-slate-300"}`} />
                {!narrow && <span className="truncate">{label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Sign out */}
        <div className="p-2 border-t border-white/10">
          <div className={`mb-2 ${narrow ? "flex justify-center" : ""}`}>
            <GuideButton tourId="admin-shell" steps={ADMIN_GUIDE_STEPS} compact={narrow} />
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
        className="min-w-0 flex-1 overflow-auto bg-[radial-gradient(circle_at_top_right,rgba(59,130,246,0.05),transparent_28%)]"
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

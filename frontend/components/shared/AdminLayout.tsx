"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Package, Users, Building2,
  BarChart2, LogOut, ChevronLeft,
} from "lucide-react";
import { logout } from "@/lib/api";
import ToastContainer from "./Toast";
import ActivityMonitor from "./ActivityMonitor";
import DeviceGate from "./DeviceGate";

const NAV = [
  { href: "/admin",          label: "Overview",   Icon: LayoutDashboard },
  { href: "/admin/batches",  label: "Batches",    Icon: Package },
  { href: "/admin/users",    label: "Users",      Icon: Users },
  { href: "/admin/clients",  label: "Clients",    Icon: Building2 },
  { href: "/analytics",      label: "Analytics",  Icon: BarChart2 },
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
    <div className="min-h-screen bg-slate-950 text-white flex">
      {/* Sidebar */}
      <aside className={`sticky top-0 h-screen flex-shrink-0 bg-slate-900 border-r border-slate-800 flex flex-col transition-all duration-200 ${narrow ? "w-14" : "w-56"}`}>

        {/* Logo + collapse toggle */}
        <div className="h-14 flex items-center justify-between px-3 border-b border-slate-800">
          {!narrow && (
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-7 h-7 rounded-md bg-blue-600 flex-shrink-0 flex items-center justify-center">
                <span className="text-xs font-bold text-white">A</span>
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold leading-tight truncate">Ardur QC</div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider">Admin</div>
              </div>
            </div>
          )}
          {narrow && (
            <div className="w-7 h-7 rounded-md bg-blue-600 flex items-center justify-center mx-auto">
              <span className="text-xs font-bold text-white">A</span>
            </div>
          )}
          {!narrow && (
            <button
              onClick={() => setNarrow(true)}
              className="rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-300"
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
            className="mx-auto mt-2 rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-300"
            title="Expand sidebar"
          >
            <ChevronLeft size={14} className="rotate-180" />
          </button>
        )}

        {/* Nav */}
        <nav className="flex-1 p-2 space-y-0.5 mt-1">
          {NAV.map(({ href, label, Icon }) => {
            const active = pathname === href || (href !== "/admin" && pathname.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                title={narrow ? label : undefined}
                className={`flex items-center gap-3 px-2.5 py-2 rounded-md text-sm transition-colors ${
                  active
                    ? "bg-blue-600/20 text-blue-300 font-medium"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                }`}
              >
                <Icon size={16} className={`flex-shrink-0 ${active ? "text-blue-400" : ""}`} />
                {!narrow && <span className="truncate">{label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Sign out */}
        <div className="p-2 border-t border-slate-800">
          <button
            onClick={handleSignOut}
            disabled={signingOut}
            title={narrow ? "Sign out" : undefined}
            className="flex items-center gap-3 w-full px-2.5 py-2 rounded-md text-sm text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors disabled:opacity-60"
          >
            <LogOut size={16} className="flex-shrink-0" />
            {!narrow && <span>{signingOut ? "Signing out…" : "Sign out"}</span>}
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0 overflow-auto">
        {children}
      </main>

      {/* Global notifications */}
      <ToastContainer />
      <ActivityMonitor />
    </div>
    </DeviceGate>
  );
}

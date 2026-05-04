"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileCheck2, HelpCircle, Inbox, LogOut } from "lucide-react";
import type { ComponentType } from "react";
import { logout } from "@/lib/api";
import ToastContainer from "./Toast";
import DeviceGate from "./DeviceGate";

export default function ReviewerLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [signingOut, setSigning] = useState(false);

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
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      {/* Top nav */}
      <header className="sticky top-0 z-30 h-14 flex-shrink-0 bg-slate-900/95 backdrop-blur border-b border-slate-800 flex items-center px-5 gap-4">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-blue-600 flex items-center justify-center">
            <span className="text-[11px] font-bold">A</span>
          </div>
          <span className="text-sm font-semibold text-slate-200">Ardur QC</span>
        </div>

        <div className="w-px h-4 bg-slate-700" />

        <nav className="flex items-center gap-1">
          <ReviewerNavLink href="/reviewer/queue" active={pathname.startsWith("/reviewer/queue")} icon={Inbox} label="Queue" />
          {pathname.startsWith("/reviewer/verify") && (
            <span className="hidden sm:inline-flex h-8 items-center gap-1.5 rounded-md border border-blue-900/50 bg-blue-950/30 px-2.5 text-sm font-medium text-blue-200">
              <FileCheck2 size={14} />
              Active review
            </span>
          )}
          <ReviewerNavLink href="/help" active={pathname === "/help"} icon={HelpCircle} label="Help" />
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <span className="text-[10px] bg-slate-800 border border-slate-700 text-slate-400 px-2 py-0.5 rounded font-mono uppercase tracking-wide">
            Reviewer
          </span>
          <button
            onClick={handleSignOut}
            disabled={signingOut}
            className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-slate-500 hover:bg-slate-800 hover:text-slate-300 transition-colors disabled:opacity-60"
          >
            <LogOut size={14} />
            {signingOut ? "…" : "Sign out"}
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-auto">
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
        active ? "bg-blue-600/20 text-blue-200 font-medium" : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
      }`}
    >
      <Icon size={14} />
      {label}
    </Link>
  );
}

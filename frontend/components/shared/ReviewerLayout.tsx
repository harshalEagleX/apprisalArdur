"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Inbox, LogOut } from "lucide-react";
import { logout } from "@/lib/api";
import ToastContainer from "./Toast";

export default function ReviewerLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [signingOut, setSigning] = useState(false);

  async function handleSignOut() {
    setSigning(true);
    await logout();
    window.location.href = "/login";
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      {/* Top nav */}
      <header className="h-14 flex-shrink-0 bg-slate-900 border-b border-slate-800 flex items-center px-5 gap-4">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-blue-600 flex items-center justify-center">
            <span className="text-[11px] font-bold">A</span>
          </div>
          <span className="text-sm font-semibold text-slate-200">Ardur QC</span>
        </div>

        <div className="w-px h-4 bg-slate-700" />

        <Link
          href="/reviewer/queue"
          className={`flex items-center gap-1.5 text-sm transition-colors ${
            pathname.startsWith("/reviewer/queue") ? "text-white font-medium" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Inbox size={14} />
          Queue
        </Link>

        <div className="ml-auto flex items-center gap-3">
          <span className="text-[10px] bg-slate-800 border border-slate-700 text-slate-400 px-2 py-0.5 rounded font-mono uppercase tracking-wide">
            Reviewer
          </span>
          <button
            onClick={handleSignOut}
            disabled={signingOut}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-300 transition-colors"
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
  );
}

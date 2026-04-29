"use client";
import { useState } from "react";
import Link from "next/link";
import { logout } from "@/lib/api";

export default function ReviewerLayout({ children }: { children: React.ReactNode }) {
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    await logout();
    window.location.href = "/login";
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      <nav className="bg-slate-900 border-b border-slate-800 px-6 py-3 flex items-center gap-4 flex-shrink-0">
        <div className="w-7 h-7 bg-blue-600 rounded-md flex items-center justify-center font-bold text-xs">
          A
        </div>
        <span className="font-semibold text-sm">Ardur QC</span>
        <span className="text-slate-600 text-sm">/</span>
        <Link href="/reviewer/queue" className="text-slate-300 text-sm hover:text-white transition-colors">
          Verification Queue
        </Link>
        <div className="ml-auto flex items-center gap-4">
          <span className="text-xs bg-amber-900/60 text-amber-300 px-2 py-0.5 rounded font-medium">
            REVIEWER
          </span>
          <button
            onClick={handleSignOut}
            disabled={signingOut}
            className="text-slate-500 hover:text-white text-sm transition-colors"
          >
            {signingOut ? "…" : "Sign out"}
          </button>
        </div>
      </nav>
      <div className="flex-1 overflow-auto">
        {children}
      </div>
    </div>
  );
}

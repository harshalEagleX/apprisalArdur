"use client";
import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle } from "lucide-react";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("Uncaught error:", error);
  }, [error]);

  return (
    <div className="foundation-grid flex min-h-screen items-center justify-center bg-slate-950 p-6 text-white">
      <div className="foundation-fade-in max-w-md rounded-lg border border-white/10 bg-[#11161C]/90 p-8 text-center shadow-[0_20px_55px_rgba(0,0,0,0.36)]">
        <AlertTriangle size={40} className="mx-auto mb-4 text-amber-400" />
        <h1 className="mb-2 text-2xl font-semibold tracking-normal">Something went wrong</h1>
        <p className="mb-2 text-sm text-slate-400">{error.message || "An unexpected error occurred."}</p>
        {error.digest && <p className="mb-6 text-xs text-slate-600">Error ID: {error.digest}</p>}
        <div className="flex justify-center gap-3">
          <button onClick={reset}
            className="rounded-md bg-blue-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500">
            Try Again
          </button>
          <Link href="/"
            className="rounded-md border border-white/10 px-5 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-white/5">
            Go Home
          </Link>
        </div>
      </div>
    </div>
  );
}

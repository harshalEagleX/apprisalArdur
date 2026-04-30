"use client";
import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle } from "lucide-react";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("Uncaught error:", error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 text-white">
      <div className="text-center max-w-md">
        <AlertTriangle size={48} className="mx-auto mb-4 text-amber-400" />
        <h1 className="text-2xl font-semibold mb-2">Something went wrong</h1>
        <p className="text-slate-400 mb-2 text-sm">{error.message || "An unexpected error occurred."}</p>
        {error.digest && <p className="text-slate-600 text-xs mb-6">Error ID: {error.digest}</p>}
        <div className="flex gap-3 justify-center">
          <button onClick={reset}
            className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors">
            Try Again
          </button>
          <Link href="/"
            className="bg-slate-700 hover:bg-slate-600 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors">
            Go Home
          </Link>
        </div>
      </div>
    </div>
  );
}

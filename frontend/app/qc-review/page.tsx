"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Legacy demo page (called the Python OCR service directly, bypassing Java auth/audit).
 * Superseded by the real reviewer workspace at /reviewer/verify/[id]. Kept as a redirect so
 * any old bookmark lands on the live review queue instead of a dead, unauthenticated page.
 */
export default function QcReviewRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/reviewer/queue"); }, [router]);
  return (
    <div className="flex h-screen items-center justify-center bg-slate-950 text-sm text-slate-500">
      Redirecting to the review queue…
    </div>
  );
}

"use client";
import { useEffect } from "react";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

export default function RootPage() {
  useEffect(() => {
    // Fetch current user role and redirect accordingly
    fetch(`${JAVA}/api/reviewer/dashboard`, { credentials: "include" })
      .then(r => {
        if (r.status === 401 || r.status === 403) {
          // Try admin
          return fetch(`${JAVA}/api/admin/dashboard`, { credentials: "include" });
        }
        window.location.href = "/reviewer/queue";
        return null;
      })
      .then(r => {
        if (!r) return;
        if (r.ok) {
          window.location.href = "/admin";
          return;
        }
        // Try client
        return fetch(`${JAVA}/api/client/dashboard`, { credentials: "include" })
          .then(cr => {
            if (cr.ok) window.location.href = "/client";
            else window.location.href = "/login";
          });
      })
      .catch(() => { window.location.href = "/login"; });
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );
}

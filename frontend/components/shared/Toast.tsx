"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, XCircle, Info, X } from "lucide-react";
import { subscribe, dismiss, type ToastItem } from "@/lib/toast";

const ICON = {
  success: CheckCircle2,
  error:   XCircle,
  notice:  Info,
  info:    Info,
};

const COLORS = {
  success: "border-green-500/30 bg-green-950/70 text-green-200",
  error:   "border-red-500/30   bg-red-950/70   text-red-200",
  notice:  "border-amber-500/30 bg-amber-950/70 text-amber-200",
  info:    "border-slate-500/25  bg-[#11161C]    text-slate-200",
};

const ICON_COLORS = {
  success: "text-green-400",
  error:   "text-red-400",
  notice:  "text-amber-400",
  info:    "text-slate-400",
};

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  useEffect(() => {
    const unsub = subscribe(setToasts);
    return () => { unsub(); };
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-80">
      {toasts.map(t => {
        const Icon = ICON[t.type];
        return (
          <div
            key={t.id}
            className={`flex items-start gap-3 rounded-lg border p-3.5 shadow-[0_18px_45px_rgba(0,0,0,0.38)] backdrop-blur ${COLORS[t.type]} animate-in slide-in-from-right-4 duration-200`}
          >
            <Icon size={16} className={`mt-0.5 flex-shrink-0 ${ICON_COLORS[t.type]}`} />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium leading-tight">{t.title}</div>
              {t.message && (
                <div className="text-xs mt-0.5 opacity-70 leading-relaxed">{t.message}</div>
              )}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="flex-shrink-0 opacity-50 hover:opacity-100 transition-opacity mt-0.5"
            >
              <X size={13} />
            </button>
          </div>
        );
      })}
    </div>
  );
}

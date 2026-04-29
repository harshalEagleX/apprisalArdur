"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, XCircle, AlertTriangle, Info, X } from "lucide-react";
import { subscribe, dismiss, type ToastItem } from "@/lib/toast";

const ICON = {
  success: CheckCircle2,
  error:   XCircle,
  warning: AlertTriangle,
  info:    Info,
};

const COLORS = {
  success: "border-green-700  bg-green-950  text-green-300",
  error:   "border-red-700   bg-red-950    text-red-300",
  warning: "border-amber-700 bg-amber-950  text-amber-300",
  info:    "border-slate-600 bg-slate-900  text-slate-200",
};

const ICON_COLORS = {
  success: "text-green-400",
  error:   "text-red-400",
  warning: "text-amber-400",
  info:    "text-blue-400",
};

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  useEffect(() => subscribe(setToasts), []);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-80">
      {toasts.map(t => {
        const Icon = ICON[t.type];
        return (
          <div
            key={t.id}
            className={`flex items-start gap-3 p-3.5 rounded-xl border shadow-2xl ${COLORS[t.type]} animate-in slide-in-from-right-4 duration-200`}
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

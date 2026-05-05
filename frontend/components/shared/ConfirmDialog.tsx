"use client";
import { useState } from "react";
import { AlertTriangle, Info } from "lucide-react";

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  danger?: boolean;
  confirmationText?: string;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  onConfirm,
  onCancel,
  danger = false,
  confirmationText,
}: Props) {
  if (!open) return null;

  return (
    <ConfirmDialogContent
      title={title}
      message={message}
      confirmLabel={confirmLabel}
      onConfirm={onConfirm}
      onCancel={onCancel}
      danger={danger}
      confirmationText={confirmationText}
    />
  );
}

function ConfirmDialogContent({
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
  danger,
  confirmationText,
}: Omit<Props, "open"> & { confirmLabel: string; danger: boolean }) {
  const [typed, setTyped] = useState("");

  const requiresTyping = Boolean(confirmationText);
  const canConfirm = !requiresTyping || typed.trim() === confirmationText;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onCancel} />
      <div
        className="relative mx-4 w-full max-w-sm rounded-lg border border-white/10 bg-[#11161C] p-5 shadow-[0_22px_60px_rgba(0,0,0,0.46)]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
      >
        <div className="flex gap-3 mb-4">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${danger ? "bg-red-950/60 border border-red-500/30" : "bg-blue-950/50 border border-blue-500/30"}`}>
            {danger ? <AlertTriangle size={16} className="text-red-400" /> : <Info size={16} className="text-blue-400" />}
          </div>
          <div>
            <h3 id="confirm-dialog-title" className="text-sm font-semibold text-white">{title}</h3>
            <p className="text-sm text-slate-400 mt-0.5 leading-relaxed">{message}</p>
          </div>
        </div>
        {requiresTyping && (
          <div className="mb-4 rounded-lg border border-red-500/20 bg-red-950/20 p-3">
            <label className="block text-xs font-medium text-red-100/80">
              Type <span className="font-mono text-red-100">{confirmationText}</span> to confirm
            </label>
            <input
              value={typed}
              onChange={event => setTyped(event.target.value)}
              autoFocus
              className="mt-2 h-9 w-full rounded-md border border-red-500/30 bg-[#0B0F14] px-3 font-mono text-sm text-red-50 placeholder:text-red-900/70 focus:outline-none focus:ring-2 focus:ring-red-500/35"
              placeholder={confirmationText}
            />
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} className="rounded-md border border-white/10 px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-white/[0.04]">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!canConfirm}
            className={`px-4 py-2 rounded-lg text-white text-sm font-medium transition-colors disabled:opacity-40 ${danger ? "bg-red-600 hover:bg-red-500" : "bg-blue-600 hover:bg-blue-500"}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

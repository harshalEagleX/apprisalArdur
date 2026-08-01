"use client";
import { useEffect, useRef } from "react";

/**
 * The shared modal shell: dim backdrop, centred panel, and the behaviour people
 * expect from a dialog — Escape closes, focus starts inside and is trapped, and
 * focus returns to whatever opened it on close.
 *
 * This exists so those rules are written once. Every dialog in the app used to
 * re-implement the backdrop and panel by hand, and each one forgot a different
 * part of the contract (no Escape, no focus trap, no focus restore), which is
 * exactly the inconsistency that makes a UI feel improvised.
 *
 * Render it only when the dialog is open — the parent owns that state.
 */
export interface ModalProps {
  children: React.ReactNode;
  onClose: () => void;
  /** id of the element naming the dialog — wire to your heading. */
  labelledBy: string;
  /** id of the element describing the dialog, when there is body copy. */
  describedBy?: string;
  /** "alertdialog" for destructive confirmations; "dialog" otherwise. */
  role?: "dialog" | "alertdialog";
  /** Tailwind max-width class for the panel. */
  maxWidth?: string;
  /** Skip the initial focus move — for panels that autofocus their own field. */
  autoFocus?: boolean;
  className?: string;
}

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

export default function Modal({
  children,
  onClose,
  labelledBy,
  describedBy,
  role = "dialog",
  maxWidth = "max-w-sm",
  autoFocus = true,
  className = "",
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    if (autoFocus) {
      const first = panelRef.current?.querySelector<HTMLElement>(FOCUSABLE);
      first?.focus();
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      opener?.focus?.();
    };
  }, [onClose, autoFocus]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div
        ref={panelRef}
        role={role}
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        className={`relative mx-4 w-full ${maxWidth} rounded-lg border border-white/10 bg-surface p-5 shadow-[0_22px_60px_rgba(0,0,0,0.46)] ${className}`}
      >
        {children}
      </div>
    </div>
  );
}

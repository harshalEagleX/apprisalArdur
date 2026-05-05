"use client"

import * as React from "react"
import { X } from "lucide-react"

import { cn } from "@/lib/utils"

export interface DialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title?: string
  description?: string
  children: React.ReactNode
  className?: string
  closeOnBackdrop?: boolean
}

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  className,
  closeOnBackdrop = true,
}: DialogProps) {
  const panelRef = React.useRef<HTMLDivElement | null>(null)
  const previousFocusRef = React.useRef<HTMLElement | null>(null)

  React.useEffect(() => {
    if (!open) return
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const timer = window.setTimeout(() => panelRef.current?.focus(), 0)
    return () => {
      window.clearTimeout(timer)
      previousFocusRef.current?.focus()
    }
  }, [open])

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault()
      onOpenChange(false)
      return
    }
    if (event.key !== "Tab") return
    const focusable = panelRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
    if (!focusable || focusable.length === 0) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={closeOnBackdrop ? () => onOpenChange(false) : undefined}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className={cn(
          "relative w-full max-w-lg rounded-lg border border-white/10 bg-[#11161C] p-5 text-slate-100 shadow-[0_22px_60px_rgba(0,0,0,0.46)] focus:outline-none",
          className
        )}
      >
        {(title || description) && (
          <div className="mb-4 pr-8">
            {title && <h2 className="text-sm font-semibold text-white">{title}</h2>}
            {description && <p className="mt-1 text-sm leading-relaxed text-slate-500">{description}</p>}
          </div>
        )}
        <button
          type="button"
          onClick={() => onOpenChange(false)}
          className="absolute right-4 top-4 inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-white/[0.05] hover:text-slate-200"
          aria-label="Close dialog"
        >
          <X size={15} />
        </button>
        {children}
      </div>
    </div>
  )
}

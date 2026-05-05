"use client"

import * as React from "react"
import { Check, ChevronDown, Search, X } from "lucide-react"

import { cn } from "@/lib/utils"

export interface SelectOption {
  value: string
  label: string
  description?: string
  disabled?: boolean
}

export interface SelectProps {
  options: SelectOption[]
  value?: string
  placeholder?: string
  searchPlaceholder?: string
  disabled?: boolean
  invalid?: boolean
  className?: string
  onValueChange: (value: string) => void
}

export function Select({
  options,
  value,
  placeholder = "Select...",
  searchPlaceholder = "Filter options...",
  disabled,
  invalid,
  className,
  onValueChange,
}: SelectProps) {
  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState("")
  const [activeIndex, setActiveIndex] = React.useState(0)
  const rootRef = React.useRef<HTMLDivElement | null>(null)
  const searchRef = React.useRef<HTMLInputElement | null>(null)

  const selected = options.find(option => option.value === value)
  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    return q
      ? options.filter(option =>
          option.label.toLowerCase().includes(q) ||
          option.value.toLowerCase().includes(q) ||
          option.description?.toLowerCase().includes(q)
        )
      : options
  }, [options, query])

  React.useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener("pointerdown", onPointerDown)
    return () => document.removeEventListener("pointerdown", onPointerDown)
  }, [open])

  React.useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => searchRef.current?.focus(), 0)
    return () => window.clearTimeout(timer)
  }, [open])

  function choose(option: SelectOption) {
    if (option.disabled) return
    onValueChange(option.value)
    setOpen(false)
    setQuery("")
    setActiveIndex(0)
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (disabled) return
    if (!open && (event.key === "Enter" || event.key === " " || event.key === "ArrowDown")) {
      event.preventDefault()
      setActiveIndex(0)
      setOpen(true)
      return
    }
    if (!open) return
    if (event.key === "Escape") {
      event.preventDefault()
      setOpen(false)
      return
    }
    if (event.key === "ArrowDown") {
      event.preventDefault()
      setActiveIndex(index => Math.min(index + 1, Math.max(filtered.length - 1, 0)))
      return
    }
    if (event.key === "ArrowUp") {
      event.preventDefault()
      setActiveIndex(index => Math.max(index - 1, 0))
      return
    }
    if (event.key === "Enter") {
      event.preventDefault()
      const option = filtered[activeIndex]
      if (option) choose(option)
    }
  }

  return (
    <div ref={rootRef} className={cn("relative", className)} onKeyDown={handleKeyDown}>
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => {
          setActiveIndex(0)
          setOpen(next => !next)
        }}
        className={cn(
          "flex h-10 w-full items-center justify-between gap-2 rounded-md border bg-[#11161C] px-3 text-left text-sm text-slate-100 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/45 disabled:cursor-not-allowed disabled:opacity-50",
          invalid
            ? "border-red-500/70 focus-visible:ring-red-500/35"
            : "border-white/10 hover:border-white/16"
        )}
      >
        <span className={cn("truncate", !selected && "text-slate-600")}>
          {selected?.label ?? placeholder}
        </span>
        <ChevronDown size={15} className={cn("shrink-0 text-slate-500 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute z-50 mt-2 w-full overflow-hidden rounded-lg border border-white/10 bg-[#11161C] shadow-[0_18px_45px_rgba(0,0,0,0.42)]">
          <div className="flex items-center gap-2 border-b border-white/10 px-2.5 py-2">
            <Search size={13} className="text-slate-600" />
            <input
              ref={searchRef}
              value={query}
              onChange={event => {
                setQuery(event.target.value)
                setActiveIndex(0)
              }}
              placeholder={searchPlaceholder}
              className="h-7 min-w-0 flex-1 bg-transparent text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none"
            />
            {query && (
              <button type="button" onClick={() => { setQuery(""); setActiveIndex(0) }} className="text-slate-600 hover:text-slate-300" aria-label="Clear filter">
                <X size={13} />
              </button>
            )}
          </div>
          <div role="listbox" className="max-h-64 overflow-y-auto p-1">
            {filtered.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs text-slate-500">No options found</div>
            ) : filtered.map((option, index) => (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={option.value === value}
                disabled={option.disabled}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => choose(option)}
                className={cn(
                  "flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                  index === activeIndex ? "bg-white/[0.05] text-white" : "text-slate-300",
                  option.value === value && "text-blue-200"
                )}
              >
                <Check size={14} className={cn("mt-0.5 shrink-0 text-blue-400", option.value === value ? "opacity-100" : "opacity-0")} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{option.label}</span>
                  {option.description && <span className="mt-0.5 block truncate text-xs text-slate-500">{option.description}</span>}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

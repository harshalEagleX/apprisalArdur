import * as React from "react"

import { cn } from "@/lib/utils"

export interface TextareaProps extends React.ComponentProps<"textarea"> {
  invalid?: boolean
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, invalid, "aria-invalid": ariaInvalid, ...props }, ref) => {
  const isInvalid = invalid || ariaInvalid === true || ariaInvalid === "true"
  return (
    <textarea
      className={cn(
        "flex min-h-[80px] w-full resize-none rounded-md border bg-[#11161C] px-3 py-2 text-sm text-slate-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] transition-colors placeholder:text-slate-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/45 disabled:cursor-not-allowed disabled:opacity-50",
        isInvalid
          ? "border-red-500/70 focus-visible:border-red-500 focus-visible:ring-red-500/35"
          : "border-white/10 hover:border-white/16 focus-visible:border-blue-500/70",
        className
      )}
      ref={ref}
      aria-invalid={isInvalid || undefined}
      {...props}
    />
  )
  }
)
Textarea.displayName = "Textarea"

export { Textarea }

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-slate-500/45",
  {
    variants: {
      variant: {
        default:
          "border-slate-500/30 bg-slate-950/45 text-slate-200",
        secondary:
          "border-white/10 bg-[#161B22] text-slate-300",
        success:
          "border-green-500/30 bg-green-950/45 text-green-200",
        warning:
          "border-amber-500/30 bg-amber-950/45 text-amber-200",
        destructive:
          "border-red-500/30 bg-red-950/45 text-red-200",
        outline: "border-white/12 bg-transparent text-slate-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }

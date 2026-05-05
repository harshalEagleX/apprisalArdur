import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-semibold tracking-normal transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0 disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "border border-blue-400/30 bg-blue-600 text-white shadow-[0_0_0_1px_rgba(59,130,246,0.22),0_0_22px_rgba(59,130,246,0.2)] hover:bg-blue-500 hover:shadow-[0_0_0_1px_rgba(59,130,246,0.36),0_0_30px_rgba(59,130,246,0.28)]",
        primary:
          "border border-blue-400/30 bg-blue-600 text-white shadow-[0_0_0_1px_rgba(59,130,246,0.22),0_0_22px_rgba(59,130,246,0.2)] hover:bg-blue-500 hover:shadow-[0_0_0_1px_rgba(59,130,246,0.36),0_0_30px_rgba(59,130,246,0.28)]",
        destructive:
          "border border-red-400/30 bg-red-600 text-white shadow-[0_0_0_1px_rgba(239,68,68,0.16),0_0_20px_rgba(239,68,68,0.16)] hover:bg-red-500",
        outline:
          "border border-white/10 bg-[#11161C] text-slate-300 hover:border-blue-500/40 hover:bg-[#161B22] hover:text-white",
        secondary:
          "border border-white/10 bg-transparent text-slate-300 hover:border-white/16 hover:bg-white/[0.04] hover:text-white",
        ghost: "text-slate-400 hover:bg-white/[0.04] hover:text-white",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 px-3 text-xs",
        lg: "h-11 px-6 text-base",
        icon: "h-10 w-10",
        "icon-sm": "h-8 w-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }

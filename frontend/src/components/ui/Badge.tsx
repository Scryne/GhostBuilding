"use client";

import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

// ── Variants ──────────────────────────────────────────────────────────────

type BadgeVariant =
  | "default"
  | "ghost"
  | "hidden"
  | "censored"
  | "discrepancy"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "outline";

const variantStyles: Record<BadgeVariant, string> = {
  default:
    "bg-white/[0.04] text-gray-300 border-white/[0.08]",
  ghost:
    "bg-ghost/10 text-ghost border-ghost/20",
  hidden:
    "bg-accent/10 text-accent border-accent/20",
  censored:
    "bg-censored/10 text-censored border-censored/20",
  discrepancy:
    "bg-discrepancy/10 text-discrepancy border-discrepancy/20",
  success:
    "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  warning:
    "bg-amber-500/10 text-amber-400 border-amber-500/20",
  danger:
    "bg-red-500/10 text-red-400 border-red-500/20",
  info:
    "bg-blue-500/10 text-blue-400 border-blue-500/20",
  outline:
    "bg-transparent text-muted border-border",
};

// ── Component ─────────────────────────────────────────────────────────────

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  dot?: boolean;
  pulse?: boolean;
  size?: "sm" | "md";
}

export default function Badge({
  className,
  variant = "default",
  dot = false,
  pulse = false,
  size = "sm",
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-semibold border rounded-full",
        "transition-colors duration-150",
        size === "sm" ? "px-2.5 py-0.5 text-[10px] uppercase tracking-wider" : "px-3 py-1 text-xs",
        variantStyles[variant],
        className
      )}
      {...props}
    >
      {dot && (
        <span className="relative flex h-1.5 w-1.5">
          {pulse && (
            <span
              className={cn(
                "absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping",
                variant === "ghost"
                  ? "bg-ghost"
                  : variant === "danger" || variant === "hidden"
                  ? "bg-red-400"
                  : variant === "success"
                  ? "bg-emerald-400"
                  : variant === "warning"
                  ? "bg-amber-400"
                  : "bg-current"
              )}
            />
          )}
          <span
            className={cn(
              "relative inline-flex rounded-full h-1.5 w-1.5",
              variant === "ghost"
                ? "bg-ghost"
                : variant === "danger" || variant === "hidden"
                ? "bg-red-400"
                : variant === "success"
                ? "bg-emerald-400"
                : variant === "warning"
                ? "bg-amber-400"
                : "bg-current"
            )}
          />
        </span>
      )}
      {children}
    </span>
  );
}

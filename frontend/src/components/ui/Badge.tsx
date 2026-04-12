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
    "bg-white/5 text-gray-300 border-white/10",
  ghost:
    "bg-ghost/10 text-ghost border-ghost/25",
  hidden:
    "bg-accent/10 text-accent border-accent/25",
  censored:
    "bg-censored/10 text-censored border-censored/25",
  discrepancy:
    "bg-discrepancy/10 text-discrepancy border-discrepancy/25",
  success:
    "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
  warning:
    "bg-yellow-500/10 text-yellow-400 border-yellow-500/25",
  danger:
    "bg-red-500/10 text-red-400 border-red-500/25",
  info:
    "bg-blue-500/10 text-blue-400 border-blue-500/25",
  outline:
    "bg-transparent text-gray-400 border-gray-600",
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
        size === "sm" ? "px-2 py-0.5 text-[10px] uppercase tracking-wider" : "px-3 py-1 text-xs",
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
                  ? "bg-yellow-400"
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
                ? "bg-yellow-400"
                : "bg-current"
            )}
          />
        </span>
      )}
      {children}
    </span>
  );
}

"use client";

import { cn } from "@/lib/utils";

// ── Component ─────────────────────────────────────────────────────────────

export interface SpinnerProps {
  /** Boyut */
  size?: "sm" | "md" | "lg" | "xl";
  /** Ek sınıf */
  className?: string;
  /** Metin */
  label?: string;
}

const sizeMap: Record<string, string> = {
  sm: "h-4 w-4 border-2",
  md: "h-6 w-6 border-2",
  lg: "h-10 w-10 border-3",
  xl: "h-14 w-14 border-4",
};

export default function Spinner({
  size = "md",
  className,
  label,
}: SpinnerProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3", className)}>
      <div
        className={cn(
          "rounded-full animate-spin",
          "border-secondary/20 border-t-secondary",
          sizeMap[size]
        )}
        role="status"
        aria-label={label || "Yükleniyor"}
      />
      {label && (
        <span className="text-sm text-muted-foreground animate-pulse">
          {label}
        </span>
      )}
    </div>
  );
}

// ── Full-page Loader ──────────────────────────────────────────────────────

export function PageLoader({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <Spinner size="xl" label={label || "Yükleniyor..."} />
    </div>
  );
}

// ── Skeleton Loader ───────────────────────────────────────────────────────

export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl bg-gradient-to-r from-surface via-surface-50 to-surface",
        "bg-[length:200%_100%] animate-shimmer",
        className
      )}
      {...props}
    />
  );
}

"use client";

import { Toaster, toast as hotToast } from "react-hot-toast";
import { cn } from "@/lib/utils";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Info,
  X,
} from "lucide-react";

// ── Toast Provider ────────────────────────────────────────────────────────

export function ToastProvider() {
  return (
    <Toaster
      position="top-right"
      gutter={8}
      toastOptions={{
        duration: 4000,
        style: {
          background: "#111827",
          color: "#F9FAFB",
          border: "1px solid #1F2937",
          borderRadius: "14px",
          padding: "12px 16px",
          fontSize: "13px",
          boxShadow:
            "0 4px 24px -4px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.03)",
          maxWidth: "420px",
        },
      }}
    />
  );
}

// ── Custom Toasts ─────────────────────────────────────────────────────────

interface ToastOptions {
  description?: string;
  duration?: number;
}

function createToast(
  type: "success" | "error" | "warning" | "info",
  title: string,
  options?: ToastOptions
) {
  const icons = {
    success: <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />,
    error: <XCircle className="w-5 h-5 text-red-400 flex-shrink-0" />,
    warning: <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0" />,
    info: <Info className="w-5 h-5 text-blue-400 flex-shrink-0" />,
  };

  const borderColors = {
    success: "border-emerald-500/20",
    error: "border-red-500/20",
    warning: "border-yellow-500/20",
    info: "border-blue-500/20",
  };

  return hotToast.custom(
    (t) => (
      <div
        className={cn(
          "flex items-start gap-3 w-full max-w-[400px]",
          "bg-surface border rounded-[14px] p-4",
          "shadow-panel",
          borderColors[type],
          t.visible ? "animate-slide-in-right" : "opacity-0 translate-x-4"
        )}
        style={{
          transition: "all 0.3s ease-out",
        }}
      >
        {icons[type]}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white leading-snug">
            {title}
          </p>
          {options?.description && (
            <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
              {options.description}
            </p>
          )}
        </div>
        <button
          onClick={() => hotToast.dismiss(t.id)}
          className="p-1 rounded-md text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors flex-shrink-0"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    ),
    {
      duration: options?.duration || 4000,
    }
  );
}

// ── Exported API ──────────────────────────────────────────────────────────

export const toast = {
  success: (title: string, options?: ToastOptions) =>
    createToast("success", title, options),
  error: (title: string, options?: ToastOptions) =>
    createToast("error", title, options),
  warning: (title: string, options?: ToastOptions) =>
    createToast("warning", title, options),
  info: (title: string, options?: ToastOptions) =>
    createToast("info", title, options),
};

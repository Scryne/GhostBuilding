"use client";

import { useEffect, useRef, useCallback, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

// ── Component ─────────────────────────────────────────────────────────────

export interface ModalProps {
  /** Modal açık mı */
  isOpen: boolean;
  /** Kapatma fonksiyonu */
  onClose: () => void;
  /** Başlık */
  title?: string;
  /** Alt başlık */
  description?: string;
  /** İçerik */
  children: ReactNode;
  /** Genişlik */
  size?: "sm" | "md" | "lg" | "xl" | "full";
  /** Overlay tıklamayla kapanır mı */
  closeOnOverlay?: boolean;
  /** Kapat butonu gösterilsin mi */
  showCloseButton?: boolean;
  /** Ek className */
  className?: string;
}

const sizeStyles: Record<string, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-2xl",
  full: "max-w-[90vw]",
};

export default function Modal({
  isOpen,
  onClose,
  title,
  description,
  children,
  size = "md",
  closeOnOverlay = true,
  showCloseButton = true,
  className,
}: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  // ── ESC tuşu ile kapatma ────────────────────────────────────────────

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [isOpen, handleKeyDown]);

  // ── Overlay tıklama ─────────────────────────────────────────────────

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (closeOnOverlay && e.target === overlayRef.current) {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className={cn(
        "fixed inset-0 z-[100] flex items-center justify-center p-4",
        "bg-black/60 backdrop-blur-sm",
        "animate-fade-in"
      )}
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? "modal-title" : undefined}
    >
      <div
        className={cn(
          "relative w-full",
          "bg-surface border border-border rounded-2xl",
          "shadow-panel",
          "animate-slide-up",
          "max-h-[85vh] overflow-y-auto custom-scrollbar",
          sizeStyles[size],
          className
        )}
      >
        {/* Header */}
        {(title || showCloseButton) && (
          <div className="sticky top-0 z-10 flex items-start justify-between p-5 pb-4 bg-surface/90 backdrop-blur-md border-b border-border/50 rounded-t-2xl">
            <div>
              {title && (
                <h2
                  id="modal-title"
                  className="text-lg font-semibold text-white"
                >
                  {title}
                </h2>
              )}
              {description && (
                <p className="mt-1 text-sm text-muted-foreground">
                  {description}
                </p>
              )}
            </div>
            {showCloseButton && (
              <button
                onClick={onClose}
                className={cn(
                  "p-1.5 rounded-lg",
                  "text-gray-400 hover:text-white",
                  "hover:bg-white/5",
                  "transition-colors duration-150",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary/50"
                )}
                aria-label="Kapat"
              >
                <X className="w-5 h-5" />
              </button>
            )}
          </div>
        )}

        {/* Content */}
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

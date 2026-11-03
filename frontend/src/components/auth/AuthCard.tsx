// ═══════════════════════════════════════════════════════════════════════════
// AuthCard — e-posta doğrulama ve şifre sıfırlama sayfalarının ortak kabuğu
// DESIGN.md: harita dışındaki sayfalarda yüzey opaktır (card) ve border ile ayrılır;
// kırmızı (accent) yalnız hata içindir, mavi (secondary) etkileşim ve bilgi içindir.
// ═══════════════════════════════════════════════════════════════════════════

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { AlertCircle, CheckCircle2, Info } from "lucide-react";
import { cn } from "@/lib/utils";

export function AuthCard({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card p-8 shadow-card-float animate-fade-in">
      <div className="mb-6 text-center">
        <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl border border-secondary/20 bg-secondary/10">
          <Icon className="h-7 w-7 text-secondary" aria-hidden="true" />
        </div>
        <h1 className="text-balance text-2xl font-bold text-foreground">{title}</h1>
        {description && (
          <p className="mt-2 text-balance text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {children}
    </div>
  );
}

type NoticeTone = "error" | "info" | "success";

const toneStyles: Record<NoticeTone, { box: string; icon: LucideIcon; iconCls: string }> = {
  error: { box: "border-accent/30 bg-accent/10 text-accent-200", icon: AlertCircle, iconCls: "text-accent-300" },
  info: { box: "border-secondary/25 bg-secondary/10 text-foreground", icon: Info, iconCls: "text-secondary-300" },
  success: { box: "border-secondary/25 bg-secondary/10 text-foreground", icon: CheckCircle2, iconCls: "text-secondary-300" },
};

/** Durum bildirimi. Hata `role="alert"`, diğerleri `role="status"` ile okunur. */
export function Notice({
  tone,
  children,
  id,
}: {
  tone: NoticeTone;
  children: ReactNode;
  id?: string;
}) {
  const style = toneStyles[tone];
  const Icon = style.icon;
  return (
    <div
      id={id}
      role={tone === "error" ? "alert" : "status"}
      className={cn("mb-6 flex items-start gap-2.5 rounded-xl border p-3 text-sm", style.box)}
    >
      <Icon className={cn("mt-0.5 h-4 w-4 flex-shrink-0", style.iconCls)} aria-hidden="true" />
      <div className="space-y-1">{children}</div>
    </div>
  );
}

export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="mt-1.5 text-xs text-accent-300">
      {message}
    </p>
  );
}

export const inputClass = (hasError: boolean, withTrailingButton = false) =>
  cn(
    "w-full rounded-xl border bg-surface py-2.5 pl-10 text-sm text-foreground",
    withTrailingButton ? "pr-11" : "pr-4",
    "placeholder:text-muted-foreground/60 transition-colors duration-200",
    "focus:outline-none focus:ring-2 focus:ring-secondary/40 focus:border-secondary/50",
    hasError ? "border-accent/50 focus:ring-accent/30" : "border-border hover:border-border-light"
  );

export const linkClass =
  "font-medium text-secondary transition-colors hover:text-secondary-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary/40 rounded";

/** Birincil düğme görünümlü bağlantı (Button'un `primary` + `lg` görünümü; iç içe <a><button> olmasın diye). */
export const primaryLinkClass = cn(
  "inline-flex w-full items-center justify-center gap-2.5 rounded-xl px-6 py-3 text-sm font-semibold text-white",
  "bg-gradient-to-r from-secondary to-secondary-600 shadow-glow-sm transition-all duration-200",
  "hover:from-secondary-400 hover:to-secondary-500 hover:shadow-glow",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary/50 focus-visible:ring-offset-2 focus-visible:ring-offset-card"
);

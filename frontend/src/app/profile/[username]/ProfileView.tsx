// ═══════════════════════════════════════════════════════════════════════════
// ProfileView.tsx — Kullanıcı profili (yalnız sahibine açık)
// Veriler /auth/me ve /auth/me/verifications'tan gelir. Eskiden bu sayfa tamamen demo
// verisiydi: hiç oy vermemiş kullanıcıya "10+ sansürlü alan doğruladınız" rozeti, 7 ülke
// ve Ankara/Moskova doğrulamaları uyduruluyordu.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import Link from "next/link";
import useSWR from "swr";
import { ArrowLeft, LogOut, ShieldAlert } from "lucide-react";
import { authApi } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import {
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  STATUS_COLORS,
  VOTE_COLORS,
  cn,
  formatDate,
  formatRelativeTime,
  formatScore,
} from "@/lib/utils";

export default function ProfileView({ username }: { username: string }) {
  const { user, isAuthenticated, isLoading, logout } = useAuth();
  const isOwn = isAuthenticated && user?.username === username;
  const { data: votes, error, isLoading: votesLoading } = useSWR(
    isOwn ? ["my-verifications", username] : null,
    () => authApi.getMyVerifications(20)
  );

  return (
    <div className="min-h-dvh bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-3">
          <Link href="/" className="flex items-center gap-2" aria-label="GhostBuilding haritası">
            <span className="rounded-lg bg-gradient-primary p-1.5">
              <ShieldAlert className="size-4 text-white" aria-hidden />
            </span>
          </Link>
          <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-foreground">
            <ArrowLeft className="size-4" aria-hidden /> Harita
          </Link>
          {isOwn && (
            <button
              type="button"
              onClick={() => logout()}
              className="ml-auto inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-white/[0.06] hover:text-foreground"
            >
              <LogOut className="size-4" aria-hidden /> Çıkış yap
            </button>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-8 px-4 py-8">
        {isLoading && <p className="text-sm text-muted" role="status">Yükleniyor…</p>}

        {!isLoading && !isOwn && (
          <section className="rounded-2xl border border-border bg-surface/70 p-6">
            <h1 className="text-lg font-semibold text-foreground">@{username}</h1>
            <p className="mt-2 max-w-prose text-sm leading-relaxed text-muted">
              Profiller yalnız sahibine açık. Doğrulama oyları bulgu sayfalarında toplu olarak
              görünür; kimin nasıl oy verdiği paylaşılmaz.
            </p>
          </section>
        )}

        {isOwn && user && (
          <>
            <section className="rounded-2xl border border-border bg-surface/70 p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h1 className="text-2xl font-bold text-foreground">{user.username}</h1>
                  <p className="mt-1 text-sm text-muted">
                    {user.email} · {formatDate(user.created_at)} tarihinde katıldı
                  </p>
                  {!user.is_verified && (
                    <p className="mt-2 text-xs text-censored">
                      E-posta adresiniz doğrulanmadı. Gelen kutunuzdaki bağlantıyı açın ya da{" "}
                      <Link href="/auth/verify-email" className="underline underline-offset-2 hover:text-foreground">
                        yeni bağlantı isteyin
                      </Link>
                      .
                    </p>
                  )}
                </div>
                <span className="rounded-full border border-border px-2.5 py-0.5 text-xs text-muted">
                  {user.role === "ADMIN" ? "Yönetici" : user.role === "MODERATOR" ? "Moderatör" : "Üye"}
                </span>
              </div>
              <dl className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
                <Stat label="Güven puanı" value={formatScore(user.trust_score)} hint="Başlangıç 50; kararla örtüşen her oy +0,5. 55'i geçince oyunuz iki kat sayılır." />
                <Stat label="Kararla örtüşen oy" value={String(user.verified_count)} hint="Bulgu doğrulanınca ya da reddedilince, kararla aynı yöndeki oylar sayılır." />
                <Stat label="Başlattığınız tarama" value={String(user.submitted_count)} />
              </dl>
            </section>

            <section aria-labelledby="votes-title" className="space-y-3">
              <h2 id="votes-title" className="text-sm font-semibold uppercase tracking-wider text-muted">
                Son oylarınız
              </h2>
              {votesLoading && <p className="text-sm text-muted" role="status">Yükleniyor…</p>}
              {error && (
                <p className="text-sm text-red-400" role="alert">
                  Oy geçmişi alınamadı. Sayfayı yenileyip yeniden deneyin.
                </p>
              )}
              {votes && votes.length === 0 && (
                <div className="rounded-2xl border border-dashed border-white/10 p-6 text-sm leading-relaxed text-muted">
                  Henüz oy vermediniz. Bir bulguyu açıp kaynak karolarını inceledikten sonra
                  “Onayla”, “Reddet” ya da “Emin değilim” diyebilirsiniz.{" "}
                  <Link href="/explore" className="text-secondary hover:text-secondary-300">
                    Bulgulara göz atın
                  </Link>
                  .
                </div>
              )}
              {votes && votes.length > 0 && (
                <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface/70">
                  {votes.map((v) => {
                    const vote = VOTE_COLORS[v.vote];
                    const status = STATUS_COLORS[v.anomaly_status];
                    return (
                      <li key={`${v.anomaly_id}-${v.created_at}`}>
                        <Link
                          href={`/explore/${v.anomaly_id}`}
                          className="flex items-center gap-3 px-4 py-3 hover:bg-white/[0.03]"
                        >
                          <span className={cn("size-2 shrink-0 rounded-full", CATEGORY_COLORS[v.category].dot)} aria-hidden />
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-foreground">
                              {v.location_label ?? `${v.lat.toFixed(4)}, ${v.lng.toFixed(4)}`}
                            </p>
                            <p className="text-xs text-muted">
                              {CATEGORY_LABELS[v.category]} · puan {formatScore(v.confidence_score)} ·{" "}
                              <span className={status.text}>{status.label}</span> · {formatRelativeTime(v.created_at)}
                            </p>
                          </div>
                          <span className={cn("shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold", vote.bg, vote.text)}>
                            {vote.label}
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-border bg-background/40 p-4">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 font-mono text-2xl font-bold tabular-nums text-foreground">{value}</dd>
      {hint && <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{hint}</p>}
    </div>
  );
}

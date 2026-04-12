// ═══════════════════════════════════════════════════════════════════════════
// VerificationPanel.tsx — Topluluk doğrulama ve oylama
// 3 oy butonu, progress bar dağılımı, son yorumlar, login guard.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useCallback, useState } from "react";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";
import {
  VerificationVote,
  type VerificationSummary,
  type VerificationItem,
} from "@/lib/types";

// ── Oy Yapılandırması ─────────────────────────────────────────────────────

const VOTE_CONFIG: Record<
  VerificationVote,
  {
    label: string;
    icon: string;
    color: string;
    bgColor: string;
    borderColor: string;
    hoverBg: string;
    glowColor: string;
  }
> = {
  [VerificationVote.CONFIRM]: {
    label: "ONAYLA",
    icon: "✓",
    color: "text-emerald-400",
    bgColor: "bg-emerald-500/8",
    borderColor: "border-emerald-500/20",
    hoverBg: "hover:bg-emerald-500/15",
    glowColor: "rgba(16, 185, 129, 0.3)",
  },
  [VerificationVote.DENY]: {
    label: "REDDET",
    icon: "✕",
    color: "text-red-400",
    bgColor: "bg-red-500/8",
    borderColor: "border-red-500/20",
    hoverBg: "hover:bg-red-500/15",
    glowColor: "rgba(239, 68, 68, 0.3)",
  },
  [VerificationVote.UNCERTAIN]: {
    label: "EMİN DEĞİLİM",
    icon: "?",
    color: "text-yellow-400",
    bgColor: "bg-yellow-500/8",
    borderColor: "border-yellow-500/20",
    hoverBg: "hover:bg-yellow-500/15",
    glowColor: "rgba(234, 179, 8, 0.3)",
  },
};

// ═══════════════════════════════════════════════════════════════════════════

interface VerificationPanelProps {
  anomalyId: string;
  summary: VerificationSummary | null;
  isLoggedIn: boolean;
  userVote?: VerificationVote | null;
  onVote?: (vote: VerificationVote, comment?: string) => Promise<void>;
  className?: string;
}

export default function VerificationPanel({
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  anomalyId,
  summary,
  isLoggedIn,
  userVote = null,
  onVote,
  className,
}: VerificationPanelProps) {
  const [activeVote, setActiveVote] = useState<VerificationVote | null>(
    userVote
  );
  const [isVoting, setIsVoting] = useState(false);
  const [comment, setComment] = useState("");
  const [showCommentInput, setShowCommentInput] = useState(false);

  // ── Oy dağılımı hesapla ───────────────────────────────────────────

  const totalVotes = summary?.total_votes ?? 0;
  const confirmCount = summary?.confirm_count ?? 0;
  const denyCount = summary?.deny_count ?? 0;
  const uncertainCount = summary?.uncertain_count ?? 0;

  const confirmPct = totalVotes > 0 ? (confirmCount / totalVotes) * 100 : 0;
  const denyPct = totalVotes > 0 ? (denyCount / totalVotes) * 100 : 0;
  const uncertainPct =
    totalVotes > 0 ? (uncertainCount / totalVotes) * 100 : 0;

  // ── Oy gönder ─────────────────────────────────────────────────────

  const handleVote = useCallback(
    async (vote: VerificationVote) => {
      if (!onVote || isVoting) return;

      setIsVoting(true);
      try {
        await onVote(vote, comment || undefined);
        setActiveVote(vote);
        setShowCommentInput(false);
        setComment("");
      } catch {
        // Error handled by parent
      } finally {
        setIsVoting(false);
      }
    },
    [onVote, isVoting, comment]
  );

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between px-1">
        <h4 className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
          Topluluk Doğrulama
        </h4>
        <span className="text-[10px] text-gray-600 tabular-nums">
          {totalVotes} oy
        </span>
      </div>

      {/* Giriş yapılmamışsa uyarı */}
      {!isLoggedIn ? (
        <div className="rounded-xl bg-white/[0.02] border border-white/5 p-4 text-center">
          <div className="w-10 h-10 rounded-full bg-secondary/10 flex items-center justify-center mx-auto mb-2">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              className="text-secondary"
            >
              <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
              <polyline points="10 17 15 12 10 7" />
              <line x1="15" y1="12" x2="3" y2="12" />
            </svg>
          </div>
          <p className="text-xs text-gray-400 mb-2">
            Oy vermek için giriş yapmanız gerekiyor
          </p>
          <button
            className={cn(
              "px-4 py-1.5 rounded-lg text-xs font-semibold",
              "bg-secondary/10 text-secondary border border-secondary/20",
              "hover:bg-secondary/20 transition-all duration-200"
            )}
            id="verification-login-btn"
          >
            Giriş Yap
          </button>
        </div>
      ) : (
        <>
          {/* Oy Butonları */}
          <div className="grid grid-cols-3 gap-2">
            {(
              [
                VerificationVote.CONFIRM,
                VerificationVote.DENY,
                VerificationVote.UNCERTAIN,
              ] as VerificationVote[]
            ).map((vote) => {
              const cfg = VOTE_CONFIG[vote];
              const isActive = activeVote === vote;

              return (
                <button
                  key={vote}
                  onClick={() => handleVote(vote)}
                  disabled={isVoting}
                  className={cn(
                    "flex flex-col items-center gap-1.5 px-2 py-3 rounded-xl",
                    "border transition-all duration-300",
                    "focus:outline-none focus-visible:ring-2 focus-visible:ring-secondary/50",
                    "disabled:opacity-50 disabled:cursor-not-allowed",
                    isActive
                      ? cn(
                          cfg.bgColor,
                          cfg.borderColor,
                          cfg.color,
                          "ring-1",
                          cfg.borderColor
                        )
                      : cn(
                          "bg-white/[0.02] border-white/5",
                          "text-gray-400",
                          cfg.hoverBg,
                          "hover:border-white/10"
                        )
                  )}
                  style={
                    isActive
                      ? {
                          boxShadow: `0 0 16px ${cfg.glowColor}`,
                        }
                      : undefined
                  }
                  id={`vote-btn-${vote.toLowerCase()}`}
                >
                  <span
                    className={cn(
                      "w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold",
                      "transition-all duration-300",
                      isActive
                        ? cn(cfg.bgColor, cfg.color)
                        : "bg-white/[0.03] text-gray-500"
                    )}
                  >
                    {cfg.icon}
                  </span>
                  <span className="text-[9px] font-bold uppercase tracking-wider">
                    {cfg.label}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Yorum ekleme */}
          {activeVote && (
            <div className="animate-fade-in">
              {!showCommentInput ? (
                <button
                  onClick={() => setShowCommentInput(true)}
                  className="text-[10px] text-secondary hover:text-secondary-300 transition-colors"
                  id="add-comment-btn"
                >
                  + Yorum ekle
                </button>
              ) : (
                <div className="space-y-2">
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Yorumunuzu yazın..."
                    rows={2}
                    className={cn(
                      "w-full px-3 py-2 rounded-lg text-xs",
                      "bg-white/[0.03] border border-white/8 text-gray-200",
                      "placeholder:text-gray-600 resize-none",
                      "focus:outline-none focus:ring-1 focus:ring-secondary/40",
                      "transition-all duration-200"
                    )}
                    id="verification-comment-input"
                  />
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Oy Dağılımı Progress Bar */}
      {totalVotes > 0 && (
        <div className="space-y-2">
          <div className="flex h-2 rounded-full overflow-hidden bg-white/[0.03]">
            {confirmPct > 0 && (
              <div
                className="bg-emerald-500/80 transition-all duration-700 ease-out"
                style={{ width: `${confirmPct}%` }}
              />
            )}
            {denyPct > 0 && (
              <div
                className="bg-red-500/80 transition-all duration-700 ease-out"
                style={{ width: `${denyPct}%` }}
              />
            )}
            {uncertainPct > 0 && (
              <div
                className="bg-yellow-500/80 transition-all duration-700 ease-out"
                style={{ width: `${uncertainPct}%` }}
              />
            )}
          </div>

          <div className="flex items-center justify-between text-[9px] text-gray-500">
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              {confirmCount} onay ({confirmPct.toFixed(0)}%)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
              {denyCount} red ({denyPct.toFixed(0)}%)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-yellow-500" />
              {uncertainCount} ({uncertainPct.toFixed(0)}%)
            </span>
          </div>
        </div>
      )}

      {/* Son Yorumlar */}
      {summary?.verifications && summary.verifications.length > 0 && (
        <div className="space-y-1.5">
          <h5 className="text-[9px] font-semibold uppercase tracking-wider text-gray-600 px-1">
            Son Yorumlar
          </h5>
          <div className="space-y-1 max-h-32 overflow-y-auto custom-scrollbar thin-scrollbar">
            {summary.verifications
              .filter((v) => v.comment)
              .slice(0, 5)
              .map((v) => (
                <CommentItem key={v.id} verification={v} />
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Yorum Satırı ─────────────────────────────────────────────────────────

function CommentItem({
  verification,
}: {
  verification: VerificationItem;
}) {
  const voteDot =
    verification.vote === VerificationVote.CONFIRM
      ? "bg-emerald-500"
      : verification.vote === VerificationVote.DENY
      ? "bg-red-500"
      : "bg-yellow-500";

  return (
    <div className="flex items-start gap-2 px-2 py-1.5 rounded-lg bg-white/[0.015] hover:bg-white/[0.03] transition-colors">
      <div className={cn("w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0", voteDot)} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span className="text-[10px] font-semibold text-gray-300 truncate">
            {verification.username}
          </span>
          {verification.is_trusted_verifier && (
            <span className="text-[8px] px-1 py-0 rounded bg-secondary/10 text-secondary border border-secondary/20 font-bold">
              ✓
            </span>
          )}
          <span className="text-[9px] text-gray-600 ml-auto flex-shrink-0">
            {formatRelativeTime(verification.created_at)}
          </span>
        </div>
        <p className="text-[10px] text-gray-400 leading-relaxed">
          {verification.comment}
        </p>
      </div>
    </div>
  );
}

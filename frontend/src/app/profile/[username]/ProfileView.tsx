// ═══════════════════════════════════════════════════════════════════════════
// ProfileView — Kullanıcı profil sayfası
// Avatar, istatistikler, rozetler, son doğrulamalar, katkı heatmap'i
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Shield,
  CheckCircle2,
  Send,
  Star,
  Award,
  Search,
  Globe,
  Ban,
  MapPin,
  Calendar,
  ExternalLink,
  TrendingUp,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { toast } from "@/components/ui/Toast";
import { PageLoader } from "@/components/ui/Spinner";
import Badge from "@/components/ui/Badge";
import { formatDate, formatRelativeTime } from "@/lib/utils";
import type { UserProfile, VerificationVote, UserRole } from "@/lib/types";

// ── Mock Data (Backend API hazır olduğunda gerçek veriyle değiştirilecek) ──

interface UserVerification {
  id: string;
  anomaly_id: string;
  anomaly_title: string;
  anomaly_category: string;
  vote: VerificationVote;
  comment: string | null;
  created_at: string;
  lat: number;
  lng: number;
  country?: string;
}

interface UserBadge {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  earned: boolean;
  earnedAt?: string;
  color: string;
  bgColor: string;
  borderColor: string;
}

interface ProfileData extends UserProfile {
  badges: UserBadge[];
  verifications: UserVerification[];
  heatmapPoints: Array<{ lat: number; lng: number; weight: number }>;
  countriesCount: number;
  censoredVerifications: number;
}

// ── Avatar Component ──────────────────────────────────────────────────────

function UserAvatar({
  username,
  size = "lg",
}: {
  username: string;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  const initials = username
    .split(/[_.\-\s]/)
    .map((part) => part[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  // Deterministik renk — kullanıcı adına göre
  const hue = useMemo(() => {
    let hash = 0;
    for (let i = 0; i < username.length; i++) {
      hash = username.charCodeAt(i) + ((hash << 5) - hash);
    }
    return Math.abs(hash) % 360;
  }, [username]);

  const sizeClasses = {
    sm: "w-8 h-8 text-xs",
    md: "w-12 h-12 text-sm",
    lg: "w-20 h-20 text-2xl",
    xl: "w-28 h-28 text-4xl",
  };

  return (
    <div
      className={`${sizeClasses[size]} rounded-full flex items-center justify-center font-bold tracking-wider select-none ring-2 ring-white/10 shadow-lg`}
      style={{
        background: `linear-gradient(135deg, hsl(${hue}, 60%, 45%), hsl(${(hue + 40) % 360}, 70%, 35%))`,
        color: `hsl(${hue}, 30%, 90%)`,
      }}
    >
      {initials}
    </div>
  );
}

// ── Stat Card ─────────────────────────────────────────────────────────────

function StatCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color: string;
}) {
  return (
    <div className="glass-panel p-4 flex flex-col items-center gap-2 hover:bg-white/[0.03] transition-colors group">
      <div
        className={`w-10 h-10 rounded-xl flex items-center justify-center ${color} transition-transform group-hover:scale-110`}
      >
        {icon}
      </div>
      <span className="text-xl font-bold text-white">{value}</span>
      <span className="text-xs text-muted-foreground text-center">{label}</span>
    </div>
  );
}

// ── Badge Card ────────────────────────────────────────────────────────────

function BadgeCard({ badge }: { badge: UserBadge }) {
  return (
    <div
      className={`relative p-4 rounded-xl border transition-all duration-300 ${
        badge.earned
          ? `${badge.bgColor} ${badge.borderColor} hover:scale-[1.03] cursor-default`
          : "bg-white/[0.02] border-white/5 opacity-40 grayscale"
      }`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
            badge.earned ? badge.bgColor : "bg-white/5"
          }`}
        >
          {badge.icon}
        </div>
        <div className="min-w-0">
          <h4
            className={`text-sm font-semibold ${
              badge.earned ? "text-white" : "text-gray-500"
            }`}
          >
            {badge.name}
          </h4>
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
            {badge.description}
          </p>
          {badge.earned && badge.earnedAt && (
            <p className="text-[10px] text-muted-foreground/60 mt-1">
              {formatRelativeTime(badge.earnedAt)} kazanıldı
            </p>
          )}
        </div>
      </div>
      {badge.earned && (
        <div className="absolute top-2.5 right-2.5">
          <CheckCircle2 className={`w-4 h-4 ${badge.color}`} />
        </div>
      )}
    </div>
  );
}

// ── Verification Item ─────────────────────────────────────────────────────

function VerificationItem({ item }: { item: UserVerification }) {
  const voteConfig = {
    CONFIRM: {
      bg: "bg-emerald-500/10",
      text: "text-emerald-400",
      label: "Onay",
      border: "border-emerald-500/20",
    },
    DENY: {
      bg: "bg-red-500/10",
      text: "text-red-400",
      label: "Red",
      border: "border-red-500/20",
    },
    UNCERTAIN: {
      bg: "bg-yellow-500/10",
      text: "text-yellow-400",
      label: "Belirsiz",
      border: "border-yellow-500/20",
    },
  };

  const vote = voteConfig[item.vote];
  const categoryIcons: Record<string, string> = {
    GHOST_BUILDING: "👻",
    HIDDEN_STRUCTURE: "🔒",
    CENSORED_AREA: "🚫",
    IMAGE_DISCREPANCY: "🔍",
  };

  return (
    <div className="group flex items-center gap-4 p-3 rounded-xl hover:bg-white/[0.03] transition-colors">
      <div
        className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm flex-shrink-0 ${vote.bg} ${vote.border} border`}
      >
        {categoryIcons[item.anomaly_category] || "?"}
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm text-white truncate">
          {item.anomaly_title || `Anomali #${item.anomaly_id.slice(0, 8)}`}
        </p>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-[10px] text-muted-foreground">
            {formatRelativeTime(item.created_at)}
          </span>
          {item.country && (
            <>
              <span className="text-muted-foreground/30">·</span>
              <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                <Globe className="w-2.5 h-2.5" />
                {item.country}
              </span>
            </>
          )}
        </div>
      </div>

      <Badge
        variant={
          item.vote === "CONFIRM"
            ? "success"
            : item.vote === "DENY"
            ? "danger"
            : "warning"
        }
        size="sm"
      >
        {vote.label}
      </Badge>

      <Link
        href={`/?anomaly=${item.anomaly_id}`}
        className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-white/5"
      >
        <ExternalLink className="w-3.5 h-3.5 text-muted-foreground" />
      </Link>
    </div>
  );
}

// ── Heatmap Placeholder ───────────────────────────────────────────────────

function ContributionHeatmap({
  points,
}: {
  points: Array<{ lat: number; lng: number; weight: number }>;
}) {
  // Basit bir grid heatmap — katkı dağılımını visualize eder
  // Gerçek harita entegrasyonu gelecek sprintte eklenecek

  const gridSize = 12;

  // Noktaları grid hücrelerine dağıt
  const grid = Array.from({ length: gridSize }, () =>
    Array.from({ length: gridSize * 3 }, () => 0)
  );

  points.forEach((point) => {
    const row = Math.floor(((point.lat + 90) / 180) * gridSize) % gridSize;
    const col =
      Math.floor(((point.lng + 180) / 360) * (gridSize * 3)) %
      (gridSize * 3);
    grid[row][col] += point.weight;
  });

  const cellMax = Math.max(...grid.flat(), 1);

  return (
    <div className="glass-panel p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <MapPin className="w-4 h-4 text-secondary" />
          Katkı Haritası
        </h3>
        <span className="text-[10px] text-muted-foreground">
          {points.length} doğrulama noktası
        </span>
      </div>

      <div className="rounded-xl overflow-hidden border border-border bg-surface/50 p-2">
        <div
          className="grid gap-[2px]"
          style={{
            gridTemplateColumns: `repeat(${gridSize * 3}, 1fr)`,
          }}
        >
          {grid.flatMap((row, ri) =>
            row.map((val, ci) => {
              const intensity = val / cellMax;
              return (
                <div
                  key={`${ri}-${ci}`}
                  className="aspect-square rounded-[2px] transition-colors"
                  style={{
                    background:
                      val > 0
                        ? `rgba(46, 109, 164, ${0.15 + intensity * 0.75})`
                        : "rgba(255, 255, 255, 0.02)",
                  }}
                  title={val > 0 ? `${val} doğrulama` : undefined}
                />
              );
            })
          )}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center justify-end gap-2 mt-3">
        <span className="text-[10px] text-muted-foreground">Az</span>
        <div className="flex gap-[2px]">
          {[0.15, 0.35, 0.55, 0.75, 0.9].map((opacity, i) => (
            <div
              key={i}
              className="w-3 h-3 rounded-[2px]"
              style={{ background: `rgba(46, 109, 164, ${opacity})` }}
            />
          ))}
        </div>
        <span className="text-[10px] text-muted-foreground">Çok</span>
      </div>
    </div>
  );
}

// ── Trust Score Visual ────────────────────────────────────────────────────

function TrustScoreRing({
  score,
  maxScore = 100,
}: {
  score: number;
  maxScore?: number;
}) {
  const percentage = (score / maxScore) * 100;
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (percentage / 100) * circumference;

  const getColor = (pct: number) => {
    if (pct >= 80) return { stroke: "#34D399", text: "text-emerald-400" };
    if (pct >= 60) return { stroke: "#FBBF24", text: "text-yellow-400" };
    if (pct >= 40) return { stroke: "#FB923C", text: "text-orange-400" };
    return { stroke: "#F87171", text: "text-red-400" };
  };

  const color = getColor(percentage);

  return (
    <div className="relative w-24 h-24">
      <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
        <circle
          cx="50"
          cy="50"
          r="40"
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth="6"
        />
        <circle
          cx="50"
          cy="50"
          r="40"
          fill="none"
          stroke={color.stroke}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-lg font-bold ${color.text}`}>
          {score.toFixed(1)}
        </span>
        <span className="text-[9px] text-muted-foreground uppercase tracking-wider">
          Trust
        </span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Main ProfileView
// ═══════════════════════════════════════════════════════════════════════════

export default function ProfileView({ username }: { username: string }) {
  const { user, isAuthenticated } = useAuth();
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const isOwnProfile = isAuthenticated && user?.username === username;

  // ── Fetch Profile ──────────────────────────────────────────────────────

  useEffect(() => {
    const loadProfile = async () => {
      setLoading(true);
      try {
        // API entegrasyonu gelecek sprint'te — şimdi demo data
        // const response = await api.get(`/users/${username}`);
        // setProfile(response.data);

        // Demo data
        await new Promise((r) => setTimeout(r, 600));

        const trustScore = isOwnProfile ? user?.trust_score ?? 62.5 : 72.3;
        const verifiedCount = isOwnProfile
          ? user?.verified_count ?? 28
          : 45;
        const submittedCount = isOwnProfile
          ? user?.submitted_count ?? 12
          : 18;

        const demoProfile: ProfileData = {
          id: "demo-id",
          email: isOwnProfile ? user?.email ?? "" : `${username}@example.com`,
          username: username,
          role: isOwnProfile ? user?.role ?? ("USER" as UserRole) : ("USER" as UserRole),
          trust_score: trustScore,
          verified_count: verifiedCount,
          submitted_count: submittedCount,
          is_active: true,
          is_verified: true,
          created_at: "2025-09-15T10:30:00Z",
          countriesCount: 7,
          censoredVerifications: 14,
          badges: [
            {
              id: "first-discovery",
              name: "İlk Keşif",
              description: "İlk anomali gönderiminizi yaptınız",
              icon: <Search className="w-5 h-5 text-ghost" />,
              earned: submittedCount > 0,
              earnedAt: "2025-10-02T14:20:00Z",
              color: "text-ghost",
              bgColor: "bg-ghost/10",
              borderColor: "border-ghost/25",
            },
            {
              id: "trusted-researcher",
              name: "Güvenilir Araştırmacı",
              description: "Trust score 4.0 üzeri başarı",
              icon: <Shield className="w-5 h-5 text-emerald-400" />,
              earned: trustScore > 4.0,
              earnedAt: "2025-11-20T09:15:00Z",
              color: "text-emerald-400",
              bgColor: "bg-emerald-500/10",
              borderColor: "border-emerald-500/25",
            },
            {
              id: "censorship-hunter",
              name: "Sansür Avcısı",
              description: "10+ CENSORED_AREA anomalisini doğruladınız",
              icon: <Ban className="w-5 h-5 text-censored" />,
              earned: 14 >= 10,
              earnedAt: "2026-01-08T16:45:00Z",
              color: "text-censored",
              bgColor: "bg-censored/10",
              borderColor: "border-censored/25",
            },
            {
              id: "global-explorer",
              name: "Küresel Kaşif",
              description: "5 farklı ülkede doğrulama yaptınız",
              icon: <Globe className="w-5 h-5 text-secondary" />,
              earned: 7 >= 5,
              earnedAt: "2026-02-14T11:30:00Z",
              color: "text-secondary",
              bgColor: "bg-secondary/10",
              borderColor: "border-secondary/25",
            },
          ],
          verifications: [
            {
              id: "v1",
              anomaly_id: "a1b2c3d4",
              anomaly_title: "Uydu görüntüsünde gizli yapı — Ankara",
              anomaly_category: "HIDDEN_STRUCTURE",
              vote: "CONFIRM" as VerificationVote,
              comment: "Net şekilde görülüyor",
              created_at: "2026-04-11T14:30:00Z",
              lat: 39.9334,
              lng: 32.8597,
              country: "Türkiye",
            },
            {
              id: "v2",
              anomaly_id: "e5f6g7h8",
              anomaly_title: "Sansürlü bölge — Moskova yakını",
              anomaly_category: "CENSORED_AREA",
              vote: "CONFIRM" as VerificationVote,
              comment: null,
              created_at: "2026-04-10T09:15:00Z",
              lat: 55.7558,
              lng: 37.6173,
              country: "Rusya",
            },
            {
              id: "v3",
              anomaly_id: "i9j0k1l2",
              anomaly_title: "Hayalet yapı tespit — İstanbul",
              anomaly_category: "GHOST_BUILDING",
              vote: "UNCERTAIN" as VerificationVote,
              comment: "Yıkım olabilir",
              created_at: "2026-04-08T18:45:00Z",
              lat: 41.0082,
              lng: 28.9784,
              country: "Türkiye",
            },
            {
              id: "v4",
              anomaly_id: "m3n4o5p6",
              anomaly_title: "Görüntü farkı — Berlin",
              anomaly_category: "IMAGE_DISCREPANCY",
              vote: "DENY" as VerificationVote,
              comment: "Farklı mevsim çekimi",
              created_at: "2026-04-05T12:00:00Z",
              lat: 52.52,
              lng: 13.405,
              country: "Almanya",
            },
            {
              id: "v5",
              anomaly_id: "q7r8s9t0",
              anomaly_title: "Gizli askeri alan — Bilinmeyen konum",
              anomaly_category: "CENSORED_AREA",
              vote: "CONFIRM" as VerificationVote,
              comment: "Coordinates match known restricted area",
              created_at: "2026-04-01T08:30:00Z",
              lat: 36.0,
              lng: 54.0,
              country: "İran",
            },
          ],
          heatmapPoints: generateDemoHeatmapPoints(),
        };

        setProfile(demoProfile);
      } catch {
        toast.error("Profil yüklenemedi", {
          description: "Lütfen sayfayı yenileyin veya daha sonra deneyin.",
        });
      } finally {
        setLoading(false);
      }
    };

    loadProfile();
  }, [username, isOwnProfile, user]);

  // ── Loading ────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <PageLoader label="Profil yükleniyor..." />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">Kullanıcı bulunamadı.</p>
        <Link
          href="/"
          className="text-secondary hover:text-secondary-300 text-sm transition-colors"
        >
          Ana sayfaya dön
        </Link>
      </div>
    );
  }

  const earnedBadges = profile.badges.filter((b) => b.earned);

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-background">
      {/* Override body overflow */}
      <style>{`body { overflow: auto !important; }`}</style>

      {/* Ambient Background */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-0 left-1/3 w-[600px] h-[400px] bg-secondary/[0.04] rounded-full blur-[120px]" />
        <div className="absolute bottom-0 right-1/4 w-[500px] h-[400px] bg-ghost/[0.03] rounded-full blur-[100px]" />
      </div>

      {/* Header Bar */}
      <header className="sticky top-0 z-30 bg-background/80 backdrop-blur-xl border-b border-border">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-3 flex items-center gap-3">
          <Link
            href="/"
            className="p-2 rounded-xl hover:bg-white/5 transition-colors"
            id="profile-back-btn"
          >
            <ArrowLeft className="w-4 h-4 text-muted-foreground" />
          </Link>
          <div>
            <h1 className="text-sm font-semibold text-white">Profil</h1>
            <p className="text-[11px] text-muted-foreground">@{username}</p>
          </div>
          {isOwnProfile && (
            <Badge variant="info" size="sm" className="ml-auto">
              Sizin Profiliniz
            </Badge>
          )}
        </div>
      </header>

      {/* Content */}
      <main className="relative z-10 max-w-5xl mx-auto px-4 sm:px-6 py-8 space-y-8">
        {/* ── Profile Header ──────────────────────────────────────────── */}
        <section className="glass-panel-strong p-6 sm:p-8 animate-fade-in">
          <div className="flex flex-col sm:flex-row items-center sm:items-start gap-6">
            {/* Avatar */}
            <div className="relative">
              <UserAvatar username={username} size="xl" />
              {profile.is_verified && (
                <div className="absolute -bottom-1 -right-1 w-7 h-7 rounded-full bg-emerald-500 border-2 border-surface flex items-center justify-center">
                  <CheckCircle2 className="w-4 h-4 text-white" />
                </div>
              )}
            </div>

            {/* Info */}
            <div className="flex-1 text-center sm:text-left">
              <div className="flex flex-col sm:flex-row sm:items-center gap-2">
                <h2 className="text-2xl font-bold text-white">{username}</h2>
                <Badge
                  variant={
                    profile.role === "ADMIN"
                      ? "danger"
                      : profile.role === "MODERATOR"
                      ? "warning"
                      : "default"
                  }
                  size="sm"
                >
                  {profile.role}
                </Badge>
              </div>

              <div className="flex flex-wrap items-center justify-center sm:justify-start gap-x-4 gap-y-1 mt-2 text-sm text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Calendar className="w-3.5 h-3.5" />
                  {formatDate(profile.created_at)} katıldı
                </span>
                {earnedBadges.length > 0 && (
                  <span className="flex items-center gap-1">
                    <Award className="w-3.5 h-3.5" />
                    {earnedBadges.length} rozet
                  </span>
                )}
              </div>

              {/* Earned badges inline */}
              {earnedBadges.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 mt-3 justify-center sm:justify-start">
                  {earnedBadges.map((badge) => (
                    <div
                      key={badge.id}
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${badge.bgColor} ${badge.borderColor} ${badge.color}`}
                      title={badge.description}
                    >
                      {badge.icon}
                      {badge.name}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Trust Score Ring */}
            <div className="flex-shrink-0">
              <TrustScoreRing score={profile.trust_score} />
            </div>
          </div>
        </section>

        {/* ── Statistics ──────────────────────────────────────────────── */}
        <section className="grid grid-cols-2 sm:grid-cols-4 gap-3 animate-slide-up">
          <StatCard
            icon={<CheckCircle2 className="w-5 h-5 text-emerald-400" />}
            label="Toplam Doğrulama"
            value={profile.verified_count}
            color="bg-emerald-500/10"
          />
          <StatCard
            icon={<Send className="w-5 h-5 text-ghost" />}
            label="Gönderilen Anomali"
            value={profile.submitted_count}
            color="bg-ghost/10"
          />
          <StatCard
            icon={<TrendingUp className="w-5 h-5 text-secondary" />}
            label="Trust Score"
            value={profile.trust_score.toFixed(1)}
            color="bg-secondary/10"
          />
          <StatCard
            icon={<Globe className="w-5 h-5 text-discrepancy" />}
            label="Ülke Sayısı"
            value={profile.countriesCount}
            color="bg-discrepancy/10"
          />
        </section>

        {/* ── Badges Section ──────────────────────────────────────────── */}
        <section className="animate-slide-up" style={{ animationDelay: "0.1s" }}>
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Award className="w-5 h-5 text-ghost" />
            Rozetler
          </h3>
          <div className="grid sm:grid-cols-2 gap-3">
            {profile.badges.map((badge) => (
              <BadgeCard key={badge.id} badge={badge} />
            ))}
          </div>
        </section>

        <div className="grid lg:grid-cols-5 gap-6">
          {/* ── Recent Verifications ──────────────────────────────────── */}
          <section
            className="lg:col-span-3 animate-slide-up"
            style={{ animationDelay: "0.2s" }}
          >
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Star className="w-5 h-5 text-secondary" />
              Son Doğrulamalar
            </h3>
            <div className="glass-panel divide-y divide-border">
              {profile.verifications.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground text-sm">
                  Henüz doğrulama yapılmamış.
                </div>
              ) : (
                profile.verifications.map((v) => (
                  <VerificationItem key={v.id} item={v} />
                ))
              )}
            </div>
          </section>

          {/* ── Heatmap ──────────────────────────────────────────────── */}
          <section
            className="lg:col-span-2 animate-slide-up"
            style={{ animationDelay: "0.3s" }}
          >
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <MapPin className="w-5 h-5 text-emerald-400" />
              Katkı Dağılımı
            </h3>
            <ContributionHeatmap points={profile.heatmapPoints} />
          </section>
        </div>
      </main>
    </div>
  );
}

// ── Demo Heatmap Data Generator ───────────────────────────────────────────

function generateDemoHeatmapPoints(): Array<{
  lat: number;
  lng: number;
  weight: number;
}> {
  const cities = [
    { lat: 41.01, lng: 28.98, weight: 8 },  // İstanbul
    { lat: 39.93, lng: 32.86, weight: 5 },  // Ankara
    { lat: 38.42, lng: 27.14, weight: 3 },  // İzmir
    { lat: 55.76, lng: 37.62, weight: 4 },  // Moskova
    { lat: 52.52, lng: 13.41, weight: 2 },  // Berlin
    { lat: 48.86, lng: 2.35, weight: 2 },   // Paris
    { lat: 36.0, lng: 54.0, weight: 3 },    // İran
    { lat: 25.2, lng: 55.27, weight: 1 },   // Dubai
    { lat: 37.57, lng: 126.98, weight: 1 }, // Seul
    { lat: 35.68, lng: 139.69, weight: 1 }, // Tokyo
    { lat: 40.71, lng: -74.01, weight: 2 }, // New York
    { lat: 51.51, lng: -0.13, weight: 2 },  // Londra
  ];

  return cities;
}

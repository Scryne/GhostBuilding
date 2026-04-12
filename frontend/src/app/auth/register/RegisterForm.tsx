// ═══════════════════════════════════════════════════════════════════════════
// RegisterForm — Yeni kullanıcı kaydı
// Email, kullanıcı adı, şifre, şifre tekrar + şifre gücü göstergesi
// react-hook-form + zod validasyon
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Eye,
  EyeOff,
  UserPlus,
  Ghost,
  Mail,
  Lock,
  User,
  Shield,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { toast } from "@/components/ui/Toast";
import Button from "@/components/ui/Button";

// ── Zod Şeması ────────────────────────────────────────────────────────────

const registerSchema = z
  .object({
    email: z
      .string()
      .min(1, "E-posta adresi gerekli")
      .email("Geçerli bir e-posta adresi girin"),
    username: z
      .string()
      .min(1, "Kullanıcı adı gerekli")
      .min(3, "Kullanıcı adı en az 3 karakter olmalı")
      .max(24, "Kullanıcı adı en fazla 24 karakter olabilir")
      .regex(
        /^[a-zA-Z0-9_]+$/,
        "Yalnızca harf, rakam ve alt çizgi kullanılabilir"
      ),
    password: z
      .string()
      .min(1, "Şifre gerekli")
      .min(8, "Şifre en az 8 karakter olmalı"),
    confirmPassword: z.string().min(1, "Şifre tekrarı gerekli"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Şifreler eşleşmiyor",
    path: ["confirmPassword"],
  });

type RegisterFormData = z.infer<typeof registerSchema>;

// ── Şifre Gücü Hesaplama ──────────────────────────────────────────────────

interface PasswordStrength {
  score: number; // 0-4
  label: string;
  color: string;
  bgColor: string;
}

function calculatePasswordStrength(password: string): PasswordStrength {
  let score = 0;

  if (password.length >= 8) score++;
  if (password.length >= 12) score++;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score++;
  if (/\d/.test(password)) score++;
  if (/[^a-zA-Z0-9]/.test(password)) score++;

  // Cap at 4
  score = Math.min(score, 4);

  const levels: PasswordStrength[] = [
    {
      score: 0,
      label: "Çok Zayıf",
      color: "text-red-400",
      bgColor: "bg-red-500",
    },
    {
      score: 1,
      label: "Zayıf",
      color: "text-orange-400",
      bgColor: "bg-orange-500",
    },
    {
      score: 2,
      label: "Orta",
      color: "text-yellow-400",
      bgColor: "bg-yellow-500",
    },
    {
      score: 3,
      label: "Güçlü",
      color: "text-emerald-400",
      bgColor: "bg-emerald-500",
    },
    {
      score: 4,
      label: "Çok Güçlü",
      color: "text-emerald-300",
      bgColor: "bg-emerald-400",
    },
  ];

  return levels[score];
}

// ═══════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════

export default function RegisterForm() {
  const router = useRouter();
  const { register: registerUser } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      email: "",
      username: "",
      password: "",
      confirmPassword: "",
    },
  });

  const watchedPassword = watch("password");
  const passwordStrength = useMemo(
    () => calculatePasswordStrength(watchedPassword || ""),
    [watchedPassword]
  );

  // ── Submit ─────────────────────────────────────────────────────────────

  const onSubmit = async (data: RegisterFormData) => {
    setApiError(null);
    try {
      const message = await registerUser({
        email: data.email,
        username: data.username,
        password: data.password,
      });
      toast.success("Kayıt başarılı!", {
        description: message || "Şimdi giriş yapabilirsiniz.",
      });
      router.push("/auth/login");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Kayıt başarısız oldu.";
      setApiError(message);
    }
  };

  // ── Input class helper ─────────────────────────────────────────────────

  const inputCls = (hasError: boolean) =>
    `w-full pl-10 pr-4 py-2.5 rounded-xl bg-surface border text-white text-sm
     placeholder:text-muted-foreground/60 transition-all duration-200
     focus:outline-none focus:ring-2 focus:ring-secondary/40 focus:border-secondary/50
     ${
       hasError
         ? "border-red-500/50 focus:ring-red-500/30"
         : "border-border hover:border-border-light"
     }`;

  const passwordInputCls = (hasError: boolean) =>
    `w-full pl-10 pr-11 py-2.5 rounded-xl bg-surface border text-white text-sm
     placeholder:text-muted-foreground/60 transition-all duration-200
     focus:outline-none focus:ring-2 focus:ring-secondary/40 focus:border-secondary/50
     ${
       hasError
         ? "border-red-500/50 focus:ring-red-500/30"
         : "border-border hover:border-border-light"
     }`;

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="glass-panel-strong p-8 animate-fade-in">
      {/* Logo / Başlık */}
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-ghost/10 border border-ghost/20 mb-4">
          <Ghost className="w-7 h-7 text-ghost" />
        </div>
        <h1 className="text-2xl font-bold text-white">Kayıt Ol</h1>
        <p className="text-sm text-muted-foreground mt-1">
          OSINT topluluğuna katılın
        </p>
      </div>

      {/* API Hatası */}
      {apiError && (
        <div
          id="register-api-error"
          className="mb-6 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-start gap-2 animate-slide-up"
        >
          <span className="block w-1.5 h-1.5 rounded-full bg-red-400 mt-1.5 flex-shrink-0" />
          {apiError}
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
        {/* Email */}
        <div>
          <label
            htmlFor="register-email"
            className="block text-sm font-medium text-gray-300 mb-1.5"
          >
            E-posta Adresi
          </label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
            <input
              id="register-email"
              type="email"
              autoComplete="email"
              placeholder="ornek@email.com"
              className={inputCls(!!errors.email)}
              {...register("email")}
            />
          </div>
          {errors.email && (
            <p className="mt-1.5 text-xs text-red-400 flex items-center gap-1">
              <span className="block w-1 h-1 rounded-full bg-red-400" />
              {errors.email.message}
            </p>
          )}
        </div>

        {/* Kullanıcı Adı */}
        <div>
          <label
            htmlFor="register-username"
            className="block text-sm font-medium text-gray-300 mb-1.5"
          >
            Kullanıcı Adı
          </label>
          <div className="relative">
            <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
            <input
              id="register-username"
              type="text"
              autoComplete="username"
              placeholder="ghost_hunter"
              className={inputCls(!!errors.username)}
              {...register("username")}
            />
          </div>
          {errors.username && (
            <p className="mt-1.5 text-xs text-red-400 flex items-center gap-1">
              <span className="block w-1 h-1 rounded-full bg-red-400" />
              {errors.username.message}
            </p>
          )}
        </div>

        {/* Şifre */}
        <div>
          <label
            htmlFor="register-password"
            className="block text-sm font-medium text-gray-300 mb-1.5"
          >
            Şifre
          </label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
            <input
              id="register-password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              placeholder="••••••••"
              className={passwordInputCls(!!errors.password)}
              {...register("password")}
            />
            <button
              type="button"
              tabIndex={-1}
              onClick={() => setShowPassword((p) => !p)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-white transition-colors"
            >
              {showPassword ? (
                <EyeOff className="w-4 h-4" />
              ) : (
                <Eye className="w-4 h-4" />
              )}
            </button>
          </div>
          {errors.password && (
            <p className="mt-1.5 text-xs text-red-400 flex items-center gap-1">
              <span className="block w-1 h-1 rounded-full bg-red-400" />
              {errors.password.message}
            </p>
          )}

          {/* Şifre Gücü Göstergesi */}
          {watchedPassword && watchedPassword.length > 0 && (
            <div className="mt-3 space-y-2 animate-slide-up">
              <div className="flex gap-1">
                {[0, 1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className={`h-1 flex-1 rounded-full transition-all duration-300 ${
                      i <= passwordStrength.score - 1
                        ? passwordStrength.bgColor
                        : "bg-white/10"
                    }`}
                  />
                ))}
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Shield className="w-3 h-3 text-muted-foreground" />
                  <span
                    className={`text-xs font-medium ${passwordStrength.color}`}
                  >
                    {passwordStrength.label}
                  </span>
                </div>
                <span className="text-[10px] text-muted-foreground">
                  {watchedPassword.length} karakter
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Şifre Tekrar */}
        <div>
          <label
            htmlFor="register-confirm-password"
            className="block text-sm font-medium text-gray-300 mb-1.5"
          >
            Şifre Tekrar
          </label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
            <input
              id="register-confirm-password"
              type={showConfirm ? "text" : "password"}
              autoComplete="new-password"
              placeholder="••••••••"
              className={passwordInputCls(!!errors.confirmPassword)}
              {...register("confirmPassword")}
            />
            <button
              type="button"
              tabIndex={-1}
              onClick={() => setShowConfirm((p) => !p)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-white transition-colors"
            >
              {showConfirm ? (
                <EyeOff className="w-4 h-4" />
              ) : (
                <Eye className="w-4 h-4" />
              )}
            </button>
          </div>
          {errors.confirmPassword && (
            <p className="mt-1.5 text-xs text-red-400 flex items-center gap-1">
              <span className="block w-1 h-1 rounded-full bg-red-400" />
              {errors.confirmPassword.message}
            </p>
          )}
        </div>

        {/* Kayıt Butonu */}
        <Button
          type="submit"
          size="lg"
          isLoading={isSubmitting}
          className="w-full"
          id="register-submit-btn"
        >
          <UserPlus className="w-4 h-4" />
          Kayıt Ol
        </Button>
      </form>

      {/* Giriş Linki */}
      <div className="mt-6 pt-6 border-t border-border text-center">
        <p className="text-sm text-muted-foreground">
          Zaten hesabınız var mı?{" "}
          <Link
            href="/auth/login"
            className="text-secondary hover:text-secondary-300 font-medium transition-colors"
          >
            Giriş Yap
          </Link>
        </p>
      </div>
    </div>
  );
}

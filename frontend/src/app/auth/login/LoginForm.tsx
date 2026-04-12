// ═══════════════════════════════════════════════════════════════════════════
// LoginForm — Email + şifre ile giriş
// react-hook-form + zod validasyon, "Beni Hatırla", şifremi unuttum (devre dışı)
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Eye, EyeOff, LogIn, Ghost, Mail, Lock } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { toast } from "@/components/ui/Toast";
import Button from "@/components/ui/Button";

// ── Zod Şeması ────────────────────────────────────────────────────────────

const loginSchema = z.object({
  email: z
    .string()
    .min(1, "E-posta adresi gerekli")
    .email("Geçerli bir e-posta adresi girin"),
  password: z
    .string()
    .min(1, "Şifre gerekli")
    .min(6, "Şifre en az 6 karakter olmalı"),
  rememberMe: z.boolean().optional(),
});

type LoginFormData = z.infer<typeof loginSchema>;

// ═══════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════

export default function LoginForm() {
  const router = useRouter();
  const { login } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      password: "",
      rememberMe: false,
    },
  });

  // ── Submit ─────────────────────────────────────────────────────────────

  const onSubmit = async (data: LoginFormData) => {
    setApiError(null);
    try {
      await login({ email: data.email, password: data.password });
      toast.success("Giriş başarılı!", {
        description: "GhostBuilding'e hoş geldiniz.",
      });
      router.push("/");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Giriş başarısız oldu.";
      setApiError(message);
    }
  };

  // ── Şifremi Unuttum ────────────────────────────────────────────────────

  const handleForgotPassword = (e: React.MouseEvent) => {
    e.preventDefault();
    toast.info("Şifre sıfırlama henüz aktif değil", {
      description:
        "Bu özellik yakında kullanıma sunulacak. Lütfen daha sonra tekrar deneyin.",
    });
  };

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="glass-panel-strong p-8 animate-fade-in">
      {/* Logo / Başlık */}
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-secondary/10 border border-secondary/20 mb-4">
          <Ghost className="w-7 h-7 text-secondary" />
        </div>
        <h1 className="text-2xl font-bold text-white">Giriş Yap</h1>
        <p className="text-sm text-muted-foreground mt-1">
          GhostBuilding platformuna erişin
        </p>
      </div>

      {/* API Hatası */}
      {apiError && (
        <div
          id="login-api-error"
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
            htmlFor="login-email"
            className="block text-sm font-medium text-gray-300 mb-1.5"
          >
            E-posta Adresi
          </label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              placeholder="ornek@email.com"
              className={`
                w-full pl-10 pr-4 py-2.5 rounded-xl
                bg-surface border text-white text-sm
                placeholder:text-muted-foreground/60
                transition-all duration-200
                focus:outline-none focus:ring-2 focus:ring-secondary/40 focus:border-secondary/50
                ${
                  errors.email
                    ? "border-red-500/50 focus:ring-red-500/30"
                    : "border-border hover:border-border-light"
                }
              `}
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

        {/* Şifre */}
        <div>
          <label
            htmlFor="login-password"
            className="block text-sm font-medium text-gray-300 mb-1.5"
          >
            Şifre
          </label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
            <input
              id="login-password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              placeholder="••••••••"
              className={`
                w-full pl-10 pr-11 py-2.5 rounded-xl
                bg-surface border text-white text-sm
                placeholder:text-muted-foreground/60
                transition-all duration-200
                focus:outline-none focus:ring-2 focus:ring-secondary/40 focus:border-secondary/50
                ${
                  errors.password
                    ? "border-red-500/50 focus:ring-red-500/30"
                    : "border-border hover:border-border-light"
                }
              `}
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
        </div>

        {/* Beni Hatırla + Şifremi Unuttum */}
        <div className="flex items-center justify-between">
          <label
            htmlFor="login-remember"
            className="flex items-center gap-2 cursor-pointer group"
          >
            <div className="relative">
              <input
                id="login-remember"
                type="checkbox"
                className="peer sr-only"
                {...register("rememberMe")}
              />
              <div className="w-4 h-4 rounded border border-border-light bg-surface transition-all peer-checked:bg-secondary peer-checked:border-secondary peer-focus-visible:ring-2 peer-focus-visible:ring-secondary/40 group-hover:border-muted-foreground" />
              <svg
                className="absolute top-0.5 left-0.5 w-3 h-3 text-white opacity-0 peer-checked:opacity-100 transition-opacity pointer-events-none"
                viewBox="0 0 12 12"
                fill="none"
              >
                <path
                  d="M2.5 6L5 8.5L9.5 3.5"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <span className="text-xs text-muted-foreground group-hover:text-gray-300 transition-colors select-none">
              Beni hatırla
            </span>
          </label>

          <button
            type="button"
            onClick={handleForgotPassword}
            className="text-xs text-secondary/70 hover:text-secondary transition-colors"
          >
            Şifremi unuttum
          </button>
        </div>

        {/* Giriş Butonu */}
        <Button
          type="submit"
          size="lg"
          isLoading={isSubmitting}
          className="w-full"
          id="login-submit-btn"
        >
          <LogIn className="w-4 h-4" />
          Giriş Yap
        </Button>
      </form>

      {/* Kayıt Ol Linki */}
      <div className="mt-6 pt-6 border-t border-border text-center">
        <p className="text-sm text-muted-foreground">
          Hesabınız yok mu?{" "}
          <Link
            href="/auth/register"
            className="text-secondary hover:text-secondary-300 font-medium transition-colors"
          >
            Kayıt Ol
          </Link>
        </p>
      </div>
    </div>
  );
}

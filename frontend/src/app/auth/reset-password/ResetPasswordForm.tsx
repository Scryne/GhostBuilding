// ═══════════════════════════════════════════════════════════════════════════
// ResetPasswordForm — e-postadaki tek kullanımlık bağlantıyla yeni şifre
// Token URL parçasından (#token=) okunur ve hemen silinir (bkz. lib/linkToken.ts).
// Başarılı sıfırlama sunucuda tüm eski oturumları kapatır; yerel oturum da temizlenir.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { CheckCircle2, Eye, EyeOff, KeyRound, Lock, LogIn, TimerOff, Unlink } from "lucide-react";
import Button from "@/components/ui/Button";
import { AuthCard, FieldError, Notice, inputClass, linkClass, primaryLinkClass } from "@/components/auth/AuthCard";
import { authApi, clearTokens, getApiError, getApiErrorCode, getApiStatus } from "@/lib/api";
import { reloadOnNewLinkToken, takeLinkToken } from "@/lib/linkToken";

// Sunucudaki kuralların aynısı (AuthService.validate_password)
const schema = z
  .object({
    password: z
      .string()
      .min(8, "Şifre en az 8 karakter olmalı")
      .max(128, "Şifre en fazla 128 karakter olabilir")
      .regex(/[A-Z]/, "Şifre en az 1 büyük harf içermeli")
      .regex(/\d/, "Şifre en az 1 rakam içermeli"),
    confirmPassword: z.string().min(1, "Şifre tekrarı gerekli"),
  })
  .refine((d) => d.password === d.confirmPassword, {
    message: "Şifreler eşleşmiyor",
    path: ["confirmPassword"],
  });

type FormData = z.infer<typeof schema>;

type State =
  | { kind: "form"; error?: string }
  | { kind: "done"; message: string }
  | { kind: "expired" }
  | { kind: "invalid" };

export default function ResetPasswordForm() {
  // Token yalnız tarayıcıda okunabilir (URL parçası sunucuya gelmez); okunur ve adresten silinir
  const [token] = useState(takeLinkToken);
  const [state, setState] = useState<State>(() => (token ? { kind: "form" } : { kind: "invalid" }));
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => reloadOnNewLinkToken(), []);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirmPassword: "" },
  });

  const onSubmit = async ({ password }: FormData) => {
    setState({ kind: "form" });
    try {
      const res = await authApi.resetPassword({ token, new_password: password });
      clearTokens(); // Bu tarayıcıdaki eski oturum da artık geçersiz
      setState({ kind: "done", message: res.message });
    } catch (err) {
      const code = getApiErrorCode(err);
      if (code === "token_expired") setState({ kind: "expired" });
      else if (code === "invalid_token") setState({ kind: "invalid" });
      else if (getApiStatus(err) === 429)
        setState({
          kind: "form",
          error: "Çok fazla deneme yapıldı. Lütfen bir süre bekleyip tekrar deneyin.",
        });
      else setState({ kind: "form", error: getApiError(err) });
    }
  };

  if (state.kind === "done") {
    return (
      <AuthCard icon={CheckCircle2} title="Şifreniz güncellendi">
        <Notice tone="success">{state.message}</Notice>
        <Link href="/auth/login" className={primaryLinkClass}>
          <LogIn className="h-4 w-4" aria-hidden="true" />
          Giriş yap
        </Link>
      </AuthCard>
    );
  }

  if (state.kind === "expired" || state.kind === "invalid") {
    const expired = state.kind === "expired";
    return (
      <AuthCard
        icon={expired ? TimerOff : Unlink}
        title={expired ? "Bağlantının süresi dolmuş" : "Bağlantı geçersiz"}
        description={
          expired
            ? "Güvenlik için sıfırlama bağlantıları kısa süre geçerlidir."
            : "Bağlantı eksik, bozuk ya da daha önce kullanılmış. Her bağlantı yalnızca bir kez çalışır."
        }
      >
        <Link href="/auth/forgot-password" className={primaryLinkClass}>
          <KeyRound className="h-4 w-4" aria-hidden="true" />
          Yeni bağlantı iste
        </Link>
        <p className="mt-6 text-center text-sm">
          <Link href="/auth/login" className={linkClass}>
            Giriş sayfasına dön
          </Link>
        </p>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      icon={KeyRound}
      title="Yeni şifre belirleyin"
      description="Şifreniz değiştiğinde açık olan tüm oturumlarınız kapanır."
    >
      {state.error && <Notice tone="error">{state.error}</Notice>}

      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
        <div>
          <label htmlFor="reset-password" className="mb-1.5 block text-sm font-medium text-foreground">
            Yeni şifre
          </label>
          <div className="relative">
            <Lock
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              id="reset-password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              aria-invalid={errors.password ? true : undefined}
              aria-describedby="reset-password-hint reset-password-error"
              className={inputClass(!!errors.password, true)}
              {...register("password")}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Şifreyi gizle" : "Şifreyi göster"}
              aria-pressed={showPassword}
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary/40"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          <p id="reset-password-hint" className="mt-1.5 text-xs text-muted-foreground">
            En az 8 karakter, 1 büyük harf ve 1 rakam.
          </p>
          <FieldError id="reset-password-error" message={errors.password?.message} />
        </div>

        <div>
          <label htmlFor="reset-confirm" className="mb-1.5 block text-sm font-medium text-foreground">
            Yeni şifre (tekrar)
          </label>
          <div className="relative">
            <Lock
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              id="reset-confirm"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              aria-invalid={errors.confirmPassword ? true : undefined}
              aria-describedby={errors.confirmPassword ? "reset-confirm-error" : undefined}
              className={inputClass(!!errors.confirmPassword)}
              {...register("confirmPassword")}
            />
          </div>
          <FieldError id="reset-confirm-error" message={errors.confirmPassword?.message} />
        </div>

        <Button type="submit" size="lg" isLoading={isSubmitting} className="w-full" id="reset-submit-btn">
          Şifremi güncelle
        </Button>
      </form>
    </AuthCard>
  );
}

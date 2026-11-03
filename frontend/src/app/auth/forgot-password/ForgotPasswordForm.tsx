// ═══════════════════════════════════════════════════════════════════════════
// ForgotPasswordForm — şifre sıfırlama bağlantısı isteği
// Yanıt hesabın var olup olmadığını söylemez; arayüz de söylemez.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { KeyRound, Mail, Send } from "lucide-react";
import Button from "@/components/ui/Button";
import { AuthCard, FieldError, Notice, inputClass, linkClass } from "@/components/auth/AuthCard";
import { authApi, getApiError, getApiErrorCode, getApiStatus } from "@/lib/api";

const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "E-posta adresi gerekli")
    .email("Geçerli bir e-posta adresi girin"),
});

type FormData = z.infer<typeof schema>;

type Outcome =
  | { kind: "sent"; message: string }
  | { kind: "disabled"; message: string }
  | { kind: "error"; message: string };

export default function ForgotPasswordForm() {
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema), defaultValues: { email: "" } });

  const onSubmit = async ({ email }: FormData) => {
    setOutcome(null);
    try {
      const res = await authApi.forgotPassword({ email });
      setOutcome({ kind: "sent", message: res.message });
    } catch (err) {
      if (getApiErrorCode(err) === "email_disabled") {
        setOutcome({ kind: "disabled", message: getApiError(err) });
      } else if (getApiStatus(err) === 429) {
        setOutcome({
          kind: "error",
          message: "Çok fazla istek gönderildi. Lütfen bir süre bekleyip tekrar deneyin.",
        });
      } else {
        setOutcome({ kind: "error", message: getApiError(err) });
      }
    }
  };

  if (outcome?.kind === "sent") {
    return (
      <AuthCard icon={Mail} title="E-postanızı kontrol edin">
        <Notice tone="success">
          <p>{outcome.message}</p>
          <p className="text-muted-foreground">
            Bağlantı kısa süre geçerlidir ve yalnızca bir kez kullanılabilir. Birkaç dakika içinde
            gelmezse adresi kontrol edip yeniden isteyebilirsiniz.
          </p>
        </Notice>
        <div className="flex flex-col gap-3 text-center text-sm">
          <button type="button" onClick={() => setOutcome(null)} className={linkClass}>
            Başka bir adres dene
          </button>
          <Link href="/auth/login" className={linkClass}>
            Giriş sayfasına dön
          </Link>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      icon={KeyRound}
      title="Şifremi unuttum"
      description="Hesabınızın e-posta adresini girin; şifrenizi yenilemeniz için bir bağlantı gönderelim."
    >
      {outcome?.kind === "disabled" && (
        <Notice tone="info" id="forgot-disabled">
          <p>{outcome.message}</p>
          <p className="text-muted-foreground">
            Bu sunucuda şifre sıfırlama şu an kullanılamıyor. Yöneticiyle iletişime geçin.
          </p>
        </Notice>
      )}
      {outcome?.kind === "error" && <Notice tone="error">{outcome.message}</Notice>}

      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
        <div>
          <label htmlFor="forgot-email" className="mb-1.5 block text-sm font-medium text-foreground">
            E-posta adresi
          </label>
          <div className="relative">
            <Mail
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              id="forgot-email"
              type="email"
              autoComplete="email"
              inputMode="email"
              placeholder="ornek@eposta.com"
              aria-invalid={errors.email ? true : undefined}
              aria-describedby={errors.email ? "forgot-email-error" : undefined}
              className={inputClass(!!errors.email)}
              {...register("email")}
            />
          </div>
          <FieldError id="forgot-email-error" message={errors.email?.message} />
        </div>

        <Button type="submit" size="lg" isLoading={isSubmitting} className="w-full" id="forgot-submit-btn">
          <Send className="h-4 w-4" aria-hidden="true" />
          Sıfırlama bağlantısı gönder
        </Button>
      </form>

      <div className="mt-6 border-t border-border pt-6 text-center text-sm text-muted-foreground">
        Şifrenizi hatırladınız mı?{" "}
        <Link href="/auth/login" className={linkClass}>
          Giriş yapın
        </Link>
      </div>
    </AuthCard>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// VerifyEmailView — e-postadaki doğrulama bağlantısının açıldığı sayfa
// Durumlar: doğrulanıyor · doğrulandı · zaten doğrulanmış · süresi dolmuş · geçersiz ·
// bağlantısız açılış (yeniden gönder) · sunucuya ulaşılamadı.
// Süresi dolmuş bağlantıda tek tıkla yeni bağlantı istenir (token'ın imzası yine doğrulanır);
// diğer durumlarda e-posta adresiyle. Yanıt hesabın varlığını söylemez.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { CheckCircle2, Mail, MailCheck, RotateCw, Send, TimerOff, Unlink } from "lucide-react";
import Button from "@/components/ui/Button";
import Spinner from "@/components/ui/Spinner";
import { AuthCard, FieldError, Notice, inputClass, linkClass, primaryLinkClass } from "@/components/auth/AuthCard";
import { authApi, getApiError, getApiErrorCode, getApiStatus } from "@/lib/api";
import { reloadOnNewLinkToken, takeLinkToken } from "@/lib/linkToken";
import type { ResendVerificationRequest } from "@/lib/types";

type Status = "verifying" | "verified" | "already_verified" | "expired" | "invalid" | "no_token" | "error";

type ResendResult = { tone: "success" | "info" | "error"; message: string } | null;

function resendErrorResult(err: unknown): NonNullable<ResendResult> {
  if (getApiErrorCode(err) === "email_disabled") {
    return {
      tone: "info",
      message: "E-posta gönderimi bu sunucuda kapalı; yeni bağlantı şu an gönderilemiyor.",
    };
  }
  if (getApiStatus(err) === 429) {
    return { tone: "error", message: "Çok fazla istek gönderildi. Lütfen bir süre bekleyip tekrar deneyin." };
  }
  return { tone: "error", message: getApiError(err) };
}

async function requestResend(body: ResendVerificationRequest): Promise<NonNullable<ResendResult>> {
  try {
    const res = await authApi.resendVerification(body);
    return { tone: "success", message: res.message };
  } catch (err) {
    return resendErrorResult(err);
  }
}

// ── Adresle yeniden gönderme formu ────────────────────────────────────────

const emailSchema = z.object({
  email: z.string().trim().min(1, "E-posta adresi gerekli").email("Geçerli bir e-posta adresi girin"),
});

function ResendByEmailForm() {
  const [result, setResult] = useState<ResendResult>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<z.infer<typeof emailSchema>>({ resolver: zodResolver(emailSchema), defaultValues: { email: "" } });

  const onSubmit = async ({ email }: { email: string }) => {
    setResult(null);
    setResult(await requestResend({ email }));
  };

  return (
    <>
      {result && <Notice tone={result.tone}>{result.message}</Notice>}
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
        <div>
          <label htmlFor="resend-email" className="mb-1.5 block text-sm font-medium text-foreground">
            E-posta adresi
          </label>
          <div className="relative">
            <Mail
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              id="resend-email"
              type="email"
              autoComplete="email"
              inputMode="email"
              placeholder="ornek@eposta.com"
              aria-invalid={errors.email ? true : undefined}
              aria-describedby={errors.email ? "resend-email-error" : undefined}
              className={inputClass(!!errors.email)}
              {...register("email")}
            />
          </div>
          <FieldError id="resend-email-error" message={errors.email?.message} />
        </div>
        <Button type="submit" size="lg" isLoading={isSubmitting} className="w-full" id="resend-submit-btn">
          <Send className="h-4 w-4" aria-hidden="true" />
          Doğrulama bağlantısını yeniden gönder
        </Button>
      </form>
    </>
  );
}

// ── Sayfa ─────────────────────────────────────────────────────────────────

export default function VerifyEmailView() {
  // Token yalnız tarayıcıda okunabilir (URL parçası sunucuya gelmez); okunur ve adresten
  // silinir, yeniden deneme için bellekte tutulur.
  const [token] = useState(takeLinkToken);
  const [status, setStatus] = useState<Status>(() => (token ? "verifying" : "no_token"));
  const [attempt, setAttempt] = useState(0);
  const [resend, setResend] = useState<ResendResult>(null);
  const [resending, setResending] = useState(false);
  const lastAttempt = useRef<number | null>(null);

  useEffect(() => reloadOnNewLinkToken(), []);

  useEffect(() => {
    if (!token || lastAttempt.current === attempt) return; // StrictMode çift çağrısına karşı
    lastAttempt.current = attempt;

    authApi
      .verifyEmail(token)
      .then((res) => setStatus(res.status))
      .catch((err) => {
        const code = getApiErrorCode(err);
        setStatus(code === "token_expired" ? "expired" : code === "invalid_token" ? "invalid" : "error");
      });
  }, [token, attempt]);

  const resendWithToken = async () => {
    setResending(true);
    setResend(await requestResend({ token }));
    setResending(false);
  };

  switch (status) {
    case "verifying":
      return (
        <AuthCard icon={MailCheck} title="E-posta adresiniz doğrulanıyor">
          <div className="flex justify-center py-2" role="status" aria-live="polite">
            <Spinner />
            <span className="sr-only">Doğrulanıyor…</span>
          </div>
        </AuthCard>
      );

    case "verified":
    case "already_verified":
      return (
        <AuthCard
          icon={CheckCircle2}
          title={status === "verified" ? "E-posta adresiniz doğrulandı" : "E-posta adresiniz zaten doğrulanmış"}
          description={
            status === "verified"
              ? "Teşekkürler. Hesabınızın e-posta adresi artık doğrulanmış olarak görünüyor."
              : "Bu bağlantı daha önce kullanılmış; yapmanız gereken başka bir şey yok."
          }
        >
          <Link href="/" className={primaryLinkClass}>
            Haritaya git
          </Link>
          <p className="mt-6 text-center text-sm">
            <Link href="/auth/login" className={linkClass}>
              Giriş yap
            </Link>
          </p>
        </AuthCard>
      );

    case "expired":
      return (
        <AuthCard
          icon={TimerOff}
          title="Bağlantının süresi dolmuş"
          description="Doğrulama bağlantıları sınırlı süre geçerlidir. Yeni bir bağlantı isteyebilirsiniz."
        >
          {resend && <Notice tone={resend.tone}>{resend.message}</Notice>}
          {resend?.tone !== "success" && (
            <Button size="lg" className="w-full" isLoading={resending} onClick={resendWithToken} id="resend-token-btn">
              <Send className="h-4 w-4" aria-hidden="true" />
              Yeni bağlantı gönder
            </Button>
          )}
        </AuthCard>
      );

    case "invalid":
      return (
        <AuthCard
          icon={Unlink}
          title="Bağlantı geçersiz"
          description="Bağlantı eksik ya da bozuk. E-postadaki bağlantıyı tam olarak kopyaladığınızdan emin olun veya yeni bir bağlantı isteyin."
        >
          <ResendByEmailForm />
        </AuthCard>
      );

    case "error":
      return (
        <AuthCard
          icon={Unlink}
          title="Doğrulama tamamlanamadı"
          description="Sunucuya ulaşılamadı ya da beklenmeyen bir hata oluştu. Bağlantınız hâlâ geçerli olabilir."
        >
          <Button size="lg" variant="secondary" className="w-full" onClick={() => {
              setStatus("verifying");
              setAttempt((n) => n + 1);
            }}>
            <RotateCw className="h-4 w-4" aria-hidden="true" />
            Tekrar dene
          </Button>
        </AuthCard>
      );

    case "no_token":
    default:
      return (
        <AuthCard
          icon={Mail}
          title="E-posta doğrulama"
          description="Kayıt olduğunuz adrese gönderilen bağlantıyı açın. E-posta gelmediyse ya da kaybolduysa yeni bir bağlantı isteyin."
        >
          <ResendByEmailForm />
          <p className="mt-6 border-t border-border pt-6 text-center text-sm">
            <Link href="/auth/login" className={linkClass}>
              Giriş sayfasına dön
            </Link>
          </p>
        </AuthCard>
      );
  }
}

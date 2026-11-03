import type { Metadata } from "next";
import ForgotPasswordForm from "./ForgotPasswordForm";

export const metadata: Metadata = {
  title: "Şifremi Unuttum",
  description: "GhostBuilding hesabınız için şifre sıfırlama bağlantısı isteyin.",
  robots: { index: false },
};

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />;
}

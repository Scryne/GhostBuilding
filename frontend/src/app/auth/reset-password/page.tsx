import type { Metadata } from "next";
import ResetPasswordFormClient from "./ResetPasswordFormClient";

export const metadata: Metadata = {
  title: "Yeni Şifre Belirle",
  description: "GhostBuilding hesabınız için yeni şifre belirleyin.",
  robots: { index: false },
  // Bağlantıdaki tek kullanımlık token hiçbir yönlendiren başlığına düşmesin
  referrer: "no-referrer",
};

export default function ResetPasswordPage() {
  return <ResetPasswordFormClient />;
}

import type { Metadata } from "next";
import VerifyEmailViewClient from "./VerifyEmailViewClient";

export const metadata: Metadata = {
  title: "E-posta Doğrulama",
  description: "GhostBuilding hesabınızın e-posta adresini doğrulayın.",
  robots: { index: false },
  referrer: "no-referrer",
};

export default function VerifyEmailPage() {
  return <VerifyEmailViewClient />;
}

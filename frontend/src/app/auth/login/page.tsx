import type { Metadata } from "next";
import LoginForm from "./LoginForm";

export const metadata: Metadata = {
  title: "Giriş Yap",
  description: "GhostBuilding platformuna giriş yapın.",
};

export default function LoginPage() {
  return <LoginForm />;
}

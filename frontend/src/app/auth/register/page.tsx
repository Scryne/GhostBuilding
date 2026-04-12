import type { Metadata } from "next";
import RegisterForm from "./RegisterForm";

export const metadata: Metadata = {
  title: "Kayıt Ol",
  description: "GhostBuilding platformuna ücretsiz kayıt olun.",
};

export default function RegisterPage() {
  return <RegisterForm />;
}

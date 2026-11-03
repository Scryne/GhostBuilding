import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Sayfa bulunamadı",
};

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-background p-6 text-center">
      <h1 className="text-2xl font-semibold text-foreground text-balance">Sayfa bulunamadı</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        Bağlantı eskimiş ya da bulgu kaldırılmış olabilir. Haritadan ya da Keşfet sayfasından devam edebilirsiniz.
      </p>
      <div className="flex gap-3">
        <Link
          href="/"
          className="rounded-lg bg-secondary px-4 py-2 text-sm font-medium text-white hover:opacity-90"
        >
          Haritaya dön
        </Link>
        <Link
          href="/explore"
          className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-card"
        >
          Keşfet
        </Link>
      </div>
    </main>
  );
}

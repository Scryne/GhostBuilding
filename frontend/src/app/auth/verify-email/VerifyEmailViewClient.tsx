"use client";

// Token URL parçasında (#token=) gelir ve yalnız tarayıcıda okunabilir; bileşen sunucuda
// önceden çizilmez, böylece ilk çizim token'ı doğrudan okur (hidrasyon uyuşmazlığı olmaz).
import dynamic from "next/dynamic";
import Spinner from "@/components/ui/Spinner";

const VerifyEmailView = dynamic(() => import("./VerifyEmailView"), {
  ssr: false,
  loading: () => (
    <div className="flex justify-center py-12" role="status">
      <Spinner />
      <span className="sr-only">Yükleniyor…</span>
    </div>
  ),
});

export default function VerifyEmailViewClient() {
  return <VerifyEmailView />;
}

/**
 * E-postadaki bağlantıdan tek kullanımlık token'ı okur ve adres çubuğundan siler.
 *
 * Backend bağlantıları `#token=…` (URL parçası) olarak kurar: parça sunucuya gönderilmez,
 * yani token nginx/Next erişim log'larına ve Referer başlığına düşmez. Eski biçim
 * (`?token=…`) de okunur. Okunduktan sonra adres temizlenir: geçmişte, yer imlerinde ya da
 * ekran paylaşımında kalmasın.
 *
 * Okunan değer sayfa yolu için önbelleklenir; böylece React'in (StrictMode) başlangıç
 * fonksiyonunu iki kez çağırması, ikinci çağrıda temizlenmiş adresten boş token okutmaz.
 * Yalnızca tarayıcıda çağrılır (sayfalar bu bileşenleri `ssr: false` ile yükler).
 */
let cached: { path: string; token: string } | null = null;

export function takeLinkToken(): string {
  if (typeof window === "undefined") return "";
  const { pathname, hash, search } = window.location;
  const fromUrl =
    new URLSearchParams(hash.slice(1)).get("token") ||
    new URLSearchParams(search).get("token");

  if (fromUrl) {
    cached = { path: pathname, token: fromUrl };
    window.history.replaceState(null, "", pathname);
    return fromUrl;
  }
  return cached?.path === pathname ? cached.token : "";
}

/**
 * Sayfa açıkken adres çubuğuna yeni bir `#token=…` yapıştırılırsa tarayıcı yeniden yüklemez
 * (yalnız parça değişir). Bu durumda sayfayı yeniden yükleyerek yeni token'ın okunmasını sağlar.
 * Temizleme fonksiyonunu döndürür (useEffect içinde kullanılır).
 */
export function reloadOnNewLinkToken(): () => void {
  const onHashChange = () => {
    if (new URLSearchParams(window.location.hash.slice(1)).get("token")) {
      window.location.reload();
    }
  };
  window.addEventListener("hashchange", onHashChange);
  return () => window.removeEventListener("hashchange", onHashChange);
}

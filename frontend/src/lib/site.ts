// Sitenin kök adresi. Tanımlı değilse yerel geliştirme adresi kullanılır: kod, sahibi
// olmadığımız bir alan adını (eskiden "ghostbuilding.dev") canonical/OG adresi yapmaz.
export const SITE_URL = (process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000").replace(/\/$/, "");

// Sunucu tarafı istekler için API adresi. Docker'da tarayıcının gördüğü adres
// (NEXT_PUBLIC_API_URL) ile konteynerin gördüğü adres farklıdır.
export const SERVER_API_URL =
  process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// MapLibre 6 çizimi bir ES modül worker'ında yapar ve worker'ı import.meta.url'e göre
// yükler. Next 16'nın paketleyicisi (Turbopack) bu dosyaları yayımlamaz; harita "Worker
// failed to load" hatasıyla boş kalır. Worker ve paylaşımlı modül public/'e kopyalanır,
// GhostMap.tsx setWorkerUrl() ile bu adresi verir. predev/prebuild'de çalışır.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const dist = join(dirname(require.resolve("maplibre-gl/package.json")), "dist");
const out = join(process.cwd(), "public", "maplibre");
mkdirSync(out, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(join(dist, file), join(out, file));
}
console.log("maplibre worker → public/maplibre/");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output for Docker multi-stage builds
  output: "standalone",

  // Image optimization — allow external tile/satellite image sources
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "tile.openstreetmap.org" },
      { protocol: "https", hostname: "mt0.google.com" },
      { protocol: "https", hostname: "mt1.google.com" },
      { protocol: "https", hostname: "ecn.t0.tiles.virtualearth.net" },
      { protocol: "https", hostname: "**.bing.com" },
      { protocol: "http", hostname: "localhost" },
    ],
    formats: ["image/avif", "image/webp"],
  },

  // Disable x-powered-by header for security
  poweredByHeader: false,

  // Strict React mode for better dev experience
  reactStrictMode: true,

  // Experimental features
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
};

export default nextConfig;

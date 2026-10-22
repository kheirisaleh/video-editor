import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

const api = process.env.STUDIO_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "Studio",
        short_name: "Studio",
        description: "TikTok product video editor",
        lang: "fa",
        dir: "rtl",
        display: "standalone",
        background_color: "#f7f3ee",
        theme_color: "#f7f3ee",
        start_url: "/",
        icons: [{ src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" }],
      },
      workbox: {
        navigateFallbackDenylist: [/^\/api\//],
        globPatterns: ["**/*.{js,css,html,svg,woff2}"],
      },
    }),
  ],
  server: {
    host: true,
    proxy: {
      "/api": { target: api, changeOrigin: true, ws: true },
    },
  },
});

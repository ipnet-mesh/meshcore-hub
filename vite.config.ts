import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

const SPA_REACT = resolve(
  __dirname,
  "src/meshcore_hub/web/static/js/spa-react",
);
const SPA_LEGACY = resolve(
  __dirname,
  "src/meshcore_hub/web/static/js/spa",
);
const DIST = resolve(__dirname, "src/meshcore_hub/web/static/dist");

export default defineConfig({
  base: "/static/dist/",
  plugins: [react()],
  resolve: {
    alias: {
      "@": SPA_REACT,
      "@legacy": SPA_LEGACY,
    },
  },
  build: {
    outDir: DIST,
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: resolve(SPA_REACT, "index.html"),
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router"],
          i18n: ["i18next", "react-i18next", "i18next-browser-languagedetector"],
        },
      },
    },
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

const SPA_REACT = resolve(
  __dirname,
  "src/meshcore_hub/web/static/js/spa-react",
);
const DIST = resolve(__dirname, "src/meshcore_hub/web/static/dist");

export default defineConfig({
  base: "/static/dist/",
  plugins: [react()],
  resolve: {
    alias: {
      "@": SPA_REACT,
    },
  },
  build: {
    outDir: DIST,
    emptyOutDir: true,
    manifest: true,
    rolldownOptions: {
      input: resolve(SPA_REACT, "index.html"),
      output: {
        codeSplitting: {
          groups: [
            {
              name: "vendor",
              test: /[\\/]node_modules[\\/](react|react-dom|react-router)[\\/]/,
            },
            {
              name: "i18n",
              test: /[\\/]node_modules[\\/](i18next|react-i18next|i18next-browser-languagedetector)[\\/]/,
            },
          ],
        },
      },
    },
  },
});

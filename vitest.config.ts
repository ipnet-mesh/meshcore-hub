import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

const SPA_REACT = resolve(
  __dirname,
  "src/meshcore_hub/web/static/js/spa-react",
);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": SPA_REACT,
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/meshcore_hub/web/static/js/spa-react/**/*.test.{ts,tsx}"],
    setupFiles: ["src/meshcore_hub/web/static/js/spa-react/test/setup.ts"],
  },
});

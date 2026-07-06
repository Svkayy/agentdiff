import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Default build: a normal, code-split SPA for hosting (Vercel/Pages). This is
// the unified marketing + dashboard app. The CLI single-file dashboard is a
// separate build — see vite.cli.config.ts (`npm run build:cli`).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 4000,
  },
});

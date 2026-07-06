import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";
import path from "node:path";

// CLI dashboard build: a single self-contained HTML file the Python CLI vendors
// (src/agentdiff/dashboard_assets/index.html) and serves offline. Entry is
// cli.html → src/cli/cli-main.tsx, which renders ONLY the local report
// dashboard (window.__AGENTDIFF__ via useReportData) — no router, no Clerk, no
// marketing content, so the single-file bundle stays lean.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  build: {
    outDir: "dist-cli",
    emptyOutDir: true,
    chunkSizeWarningLimit: 4000,
    rollupOptions: {
      input: path.resolve(__dirname, "cli.html"),
    },
  },
});

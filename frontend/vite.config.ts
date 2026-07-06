import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Default build: a normal, code-split SPA for hosting (Vercel/Pages). This is
// the unified marketing + dashboard app. The CLI single-file dashboard is a
// separate build — see vite.cli.config.ts (`npm run build:cli`).
const isGitHubPagesBuild = process.env.AGENTDIFF_GITHUB_PAGES === "true";

export default defineConfig({
  plugins: [react()],
  base: isGitHubPagesBuild ? "/agentdiff/" : "/",
  // Load env from the repo root so VITE_CLERK_PUBLISHABLE_KEY in Repo/.env is
  // picked up; only VITE_-prefixed vars are exposed to the client.
  envDir: path.resolve(__dirname, ".."),
  server: {
    // Honor an externally assigned port (preview harnesses set PORT);
    // Vite's default 5173 fallback applies when PORT is unset.
    port: process.env.PORT ? Number(process.env.PORT) : undefined,
    strictPort: !!process.env.PORT,
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 4000,
  },
});

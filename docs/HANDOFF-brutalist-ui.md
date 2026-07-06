# AgentDiff — Brutalist UI Rework: Handoff

**Date:** 2026-07-05 · **Branch:** `feat/brutalist-ui` · **Repo:** `/Users/sandeepvinay.sk/CMU/AgentDiff/Repo`

## What this project is
AgentDiff = behavioral regression testing for AI agents (Python engine + hosted FastAPI/Postgres/Redis platform + React dashboard + marketing site). The engine/server are DONE and merged (branch `feat/report-ui`, merge `5c736c6`). This branch is a **UI-only** rework: restyle the landing + dashboard to a brutalist design, and unify them into ONE Vite app served from one link (Vercel-transferable). **Do not touch the Python engine or server/** in this work.

## Current git state
- Branch `feat/brutalist-ui`, based on `feat/report-ui` @ `5c736c6`.
- Commits so far (oldest→newest):
  - `8a00660` plan
  - `a75e0f6` + `5818e28` — **T1 DONE** (unify into one SPA)
  - `c7f9ff7` + `223db9d` — **T2 DONE** (design foundation + DESIGN.md)
  - `aa2435b` — **WIP checkpoint** (T3+T4 in-flight restyle, unreviewed but BUILDS CLEAN)
- Plan: `docs/superpowers/plans/2026-07-05-brutalist-ui.md` (READ THIS — 5 tasks T1–T5).
- Full running ledger (on disk, gitignored): `.superpowers/sdd/progress.md` — authoritative status + every decision.

## Task status
- **T1 DONE + reviewed** — marketing + dashboard are ONE Vite SPA. Public routes `/`, `/docs`, `/docs/:slug`, `/privacy`, `/terms` render WITHOUT Clerk; gated `/projects`, `/projects/:id`, `/runs/:id` behind `RequireAuth` (ClerkProvider mounts only there). Projects list moved `/`→`/projects`. `vercel.json` added (SPA rewrite). Build split: `npm run build` = normal SPA (hosting); `npm run build:cli` = self-contained single-file CLI dashboard (vendored by `src/agentdiff/dashboard.py` + `.github/workflows/release.yml`).
- **T2 DONE + reviewed** — brutalist tokens (verbatim from template), JetBrains Mono body + **Silkscreen** `font-pixel` (Geist Pixel is Next-only, unusable in Vite), dot-grid bg, glitch/marquee/blink keyframes, primitives in `frontend/src/components/system/` (ScrambleText, SectionLabel, ThemeToggle, useTheme). Legacy tokens aliased so un-restyled components still render. **DESIGN.md rewritten = governing spec.** Pre-paint theme script in `frontend/index.html` (no dark-mode flash).
- **T3 IN-FLIGHT (WIP in `aa2435b`, NOT reviewed)** — marketing restyle. New components exist: `frontend/src/pages/marketing/components/{Navbar,HeroSection,FeatureGrid,AboutSection,GlitchMarquee,BrutalistFooter,WorkflowDiagram}.tsx` + `bento/`. **Needs finishing + review against the user requirements below.**
- **T4 IN-FLIGHT (WIP in `aa2435b`, NOT reviewed)** — dashboard restyle (chrome only, zero functional change). Edits across Shell, ProjectsPage, ProjectPage, RunDetailPage, sections/*, components/. **Needs finishing + review; all 41 vitest must stay green.**
- **T5 PENDING** — retire `landing/` app (after content-parity check), replace `deploy-landing.yml`, document the Vercel deploy path in `docs/deploy-production.md`, README/CHANGELOG, whole-branch review, finish.

## USER REQUIREMENTS — binding, apply to T3/T4 (these override the template)
1. **Legibility (both surfaces):** all text clearly visible, NOT tiny. Micro-labels/section-tags ≥ 11–12px (text-[11px]/text-xs) with wide tracking; body/table/card text ≥ text-sm; docs prose text-base. Verify `muted-foreground` contrast on cream (light) AND on dark cards — nothing barely-visible gray-on-cream. The template's `text-[10px]` is TOO SMALL — override it.
2. **Methodology/About section = a REAL agent graph, not an abstract visual.** Left panel must render an actual SVG agent-topology diagram of AgentDiff's concept: orchestrator → retriever / fact_checker / summarizer (with tool leaves), baseline→candidate, and one sub-agent node in the "after" state highlighted **solid `#ea580c` as STOPPED** (the product's signature visual). Square bordered nodes, mono labels, real edges. Static SVG is fine. Label it truthfully (e.g. `AGENT_GRAPH: baseline → candidate`). NOT a dither/abstract composition.
3. **Keep it OPEN SOURCE** (user reverted an earlier "make it a product" instruction). OSS framing is fine: GitHub links / "star on GitHub" / MIT mentions allowed; keep the **Codebase Map** doc in the docs portal. (Earlier instructions to scrub OSS framing + remove Codebase Map are WITHDRAWN.)
4. **REMOVE the pricing section entirely** — no PricingSection, no "Pricing" nav/footer link, no `#pricing` anchor. Renumber section indices to stay sequential without it.
5. **Content must be truthful** (no invented metrics): real provider list (OpenAI/Anthropic/Google/Mistral/Bedrock/Cohere/Azure/Ollama + LangGraph/CrewAI adapters), real product figures (8 provider parsers, 4 framework adapters, ~540 tests, α=0.05 stats). Decorative tick counters OK; fake "12.8B calls / uptime" presented as real is NOT.
6. Primary CTA everywhere = **"Open Dashboard" → /projects** (in-app, same SPA).

## Reference material
- Design template (the aesthetic being copied), extracted at: `/private/tmp/claude-501/-Users-sandeepvinay-sk-CMU-AgentDiff/4a2fd1e3-0469-4739-b9d8-915496dcc51b/scratchpad/template/` — `app/globals.css` (tokens), `components/*.tsx` (navbar/hero/workflow-diagram/feature-grid/about-section/glitch-marquee/footer/theme-toggle/topology-graph). If that scratchpad is gone, the design is fully specified in `DESIGN.md`.
- The user's original prose spec for the template is in the chat that produced this handoff.

## How to run / verify
- Gates (MANDATORY before any commit): `npm --prefix frontend run build` (tsc+vite) green; `npm --prefix frontend run test` green (**41 tests**); `npm --prefix frontend run build:cli` green + produces a self-contained `frontend/dist-cli/cli.html`.
- The hosted stack is running via Docker (`docker compose up -d` already done): dashboard http://localhost:5173, API http://localhost:8000 (`/health` OK, 4 projects/8 runs of demo data). `.env` holds dev Clerk + Fernet secrets — do NOT print or commit them.
- Marketing/public routes render without Clerk. Authenticated dashboard pages need Clerk sign-in; to visually verify the restyled five-view REPORT without Clerk, open the `build:cli` output (`dist-cli/cli.html`) which renders the sections against a bundled sample payload.
- Preview: `npm --prefix frontend run preview` (built) or `dev`. NOTE the old `landing/` dev server collides with Docker's dashboard on :5173 — but landing is being retired; use the unified `frontend/` app.

## Immediate next steps (recommended order)
1. **Review the WIP `aa2435b`** against USER REQUIREMENTS 1–6. The likely gaps: pricing may still be present (must be removed), Methodology graph may be abstract (must be the real agent topology), text may be too small in places, OSS framing must be intact, Codebase Map present.
2. **Finish/fix T3 (marketing)** and **T4 (dashboard)** to satisfy those, keeping all 41 tests green and all three builds passing. Restyle is chrome-only for the dashboard — do not change behavior; preserve every loading/error/empty state, modal, keyboard handler, aria-label, and the verdict color mapping (pass = neutral/foreground, warn = orange outline, fail = solid `#ea580c` — must stay instantly distinguishable).
3. **T5:** delete `landing/` after confirming docs/privacy/terms/SEO parity in `frontend/`; replace `.github/workflows/deploy-landing.yml` with a unified-frontend deploy; document Vercel in `docs/deploy-production.md` ("import repo, root = frontend/, set VITE_CLERK_PUBLISHABLE_KEY + VITE_AGENTDIFF_API_URL, deploy" — note the API/Postgres/Redis stay on Docker/self-host, Vercel only hosts the UI); update README + CHANGELOG.
4. Final whole-repo build/test pass; verify one-link flow (`/` → "Open Dashboard" → sign-in wall → projects). Merge `feat/brutalist-ui` → `feat/report-ui` (or open a PR).

## Gotchas
- The `frontend/` app uses `vite-plugin-singlefile` ONLY for `build:cli`; the default build is a normal code-split SPA. Don't reintroduce singlefile into the default build.
- Two background restyle agents were mid-run when this handoff was cut; the WIP commit `aa2435b` is their last-captured state (builds clean). If they wrote more after the snapshot, it's uncommitted in the tree — check `git status`.
- `.superpowers/` is gitignored (build ledger/reports) — read `.superpowers/sdd/progress.md` on disk for full history.

## UPDATE (T4 landed after this doc was first written)
- **T4 (dashboard restyle) is now COMMITTED** as `b00b2b5` — chrome-only, verdict mapping implemented (pass = neutral/foreground outline, warn = orange `#ea580c` OUTLINE, fail = solid, stopped-node = solid-orange plate), legibility feedback applied (no text below `text-xs`/12px). Branch tip `b00b2b5` **builds clean, 41/41 tests pass, build:cli OK.** BUT it is **NOT independently reviewed** — review it against user requirements (esp. functional preservation + verdict distinguishability) before merge.
- **T3 (marketing) may still be running** when you pick this up — check `git status` and `git log` for a `feat(marketing): ...` commit on top of `b00b2b5`. If T3's commit is absent, its work is the WIP in `aa2435b` and needs finishing per USER REQUIREMENTS 1–6 (esp. **remove pricing**, **real methodology agent-graph**, **keep open-source framing**, legibility).
- **MUST-FIX BUG (surfaced by T4, pre-existing, not yet fixed):** the CLI single-file dashboard crashes on its SAMPLE fallback. `frontend/src/lib/payload.ts` returns `frontend/src/sample.json` raw, but that sample lacks the `skipped_checks` field, so `RigorBanners` throws when `agentdiff dashboard` renders with no injected payload. Fix: either regenerate `sample.json` with the current payload shape (it has `run_metrics`/`warnings`/`skipped_checks`/`confidence` — see `report_payload.build()`), or make `RigorBanners`/the adapter tolerate a missing `skipped_checks` (default to `[]`). This is in the CLI-report path (`cli/CliReport.tsx` → `useReportData()`), which real `build:cli` output exercises.

# Brutalist UI Rework + One-Link Unification — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task. Checkbox (`- [ ]`) steps.

**Goal:** Restyle AgentDiff's landing page AND dashboard to the brutalist "SYS.INT" design language (user-supplied template), and unify both surfaces into ONE Vite app served from one link, Vercel-transferable.

**Reference template (READ THE ACTUAL CODE, not just the prose):** extracted at
`/private/tmp/claude-501/-Users-sandeepvinay-sk-CMU-AgentDiff/4a2fd1e3-0469-4739-b9d8-915496dcc51b/scratchpad/template/` — key files: `app/globals.css`, `app/page.tsx`, `components/{navbar,hero-section,workflow-diagram,feature-grid,about-section,pricing-section,glitch-marquee,footer,theme-toggle}.tsx`. The user's prose spec (same design) is in the conversation; the code is authoritative for visual details.

**Architecture decisions (locked):**
- ONE app: merge marketing (landing) into `frontend/` as public routes of the existing Vite SPA. Public: `/` (marketing), `/docs`, `/docs/:slug`, `/privacy`, `/terms`. Clerk-gated: `/projects`, `/projects/:id`, `/runs/:id` (gate moves from app-wide to route-level; unauthenticated visits to gated routes show Clerk sign-in). One dev server, one build, ONE LINK.
- STAY ON VITE (no Next.js migration): Vercel hosts Vite SPAs natively. Adapt Next-isms: `next-themes` → small `useTheme` hook (class on `<html>` + localStorage, default light, no system); `next/font` → Fontsource `@fontsource/jetbrains-mono` (or Google Fonts link) for body; display "pixel" font: try the `geist` npm package's Pixel woff2 imported via Vite; if not importable, use a close pixel Google font (e.g. "Silkscreen") as `font-pixel`.
- CONTENT IS AGENTDIFF, not SYS.INT. Adapt copy truthfully: hero e.g. "CAPTURE. COMPARE." / "ATTRIBUTE." ; workflow diagram center node = the agent, left pills Capture/Sample/Record, right pills Compare/Attribute/Alert; marquee = provider ecosystem AgentDiff actually supports (OPENAI, ANTHROPIC, GOOGLE, MISTRAL, BEDROCK, COHERE, AZURE, OLLAMA, LANGGRAPH, CREWAI); pricing tiers = the REAL plans from the quota system (FREE $0 500 runs/mo, PRO, ENTERPRISE custom — check server/usage.py + docs for truthful limits); metrics/stats cards use TRUTHFUL product figures (8 provider parsers, 4 framework adapters, 500+ tests, p<0.05 stats etc.) — NO invented usage numbers (no fake "12.8B calls" / uptime counters presented as real; a clearly-decorative tick counter is fine).
- Verdict semantics preserved: pass/warn/fail must stay visually distinguishable in the dashboard. Map: pass = foreground/neutral chip, warn = orange OUTLINE, fail = solid orange `#ea580c`. Data-viz (graph, deltas) keeps meaningfully distinct states within the cream/black/orange palette.
- DESIGN.md is REWRITTEN to codify the new system (CLAUDE.md says DESIGN.md governs; user explicitly ordered the new aesthetic — the old doc must not survive contradicting it).
- Vercel: `frontend/vercel.json` SPA rewrite; envs documented (VITE_CLERK_PUBLISHABLE_KEY, VITE_AGENTDIFF_API_URL). HONEST NOTE in docs: Vercel hosts the one-link UI; the API/worker/Postgres/Redis remain Docker/self-hosted — VITE_AGENTDIFF_API_URL points at wherever that runs.
- IMPORTANT: frontend still uses vite-plugin-singlefile for the CLI dashboard vendoring — check whether the merged app breaks that; if marketing content bloats the single-file build, split builds (default SPA build for hosting + a separate `build:cli` single-file entry for the vendored dashboard) and update release.yml accordingly.
- `landing/` app: retire after port — replace `deploy-landing.yml` with a workflow that builds `frontend/` (or delete the workflow and rely on Vercel), and delete `landing/` in the final task once T3 confirms full content parity (docs registry, privacy/terms, SEO meta all ported).

## Global Constraints
- Gates every task: `npm --prefix frontend run build` + `npm --prefix frontend run test` (41 vitest must stay green; add tests where logic is added). Landing build gate applies only until `landing/` is retired.
- Commit per task, explicit paths, trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Retry index.lock 2s x3.
- Never print `.env` values. Engine/server untouched (UI-only build) except release.yml if the single-file split requires it.

### Task T1: One-app unification (no restyle)
Files: frontend/src/{App,main}.tsx, new frontend/src/pages/marketing/* (ported AS-IS from landing/src: Nav/Hero/Features/HowItWorks/Integrations/SlackBrief/Footer + DocsPage + registry + privacy/terms content), frontend/index.html (merge SEO/OG/JSON-LD/favicon from landing/index.html), frontend/vercel.json (new), frontend/package.json (add marked/dompurify + framer-motion deps used by ported code).
- Route map: `/` marketing home; `/docs`, `/docs/:slug`, `/privacy`, `/terms` public (React Router paths — replace the landing hash-router with real routes; keep heading-anchor behavior); existing `/projects`... routes Clerk-gated via a `<RequireAuth>` wrapper (SignedIn/SignedOut per-route), NOT an app-wide gate; `MissingClerkConfig` only blocks gated routes.
- Marketing "Sign in"/"Get started" CTAs now navigate to `/projects` (same app!) instead of an external APP_URL.
- Docs registry glob paths re-based for frontend/ location; tolerant-of-missing behavior preserved.
- Gates + verify `/`, `/docs`, `/projects` (sign-in wall) render via preview tools. Single-file/CLI vendoring checked (see decision above).
- Commit: `feat(app): unify marketing + dashboard into one SPA with public/gated routes`

### Task T2: Design foundation
Files: frontend/src/index.css (new token set: HSL vars light/dark per template globals.css, radius 0, dot-grid-bg, glitch/marquee/blink keyframes), frontend/tailwind.config.js (map tokens; font-mono JetBrains, font-pixel display; sharp corners default), frontend/package.json (fonts, lucide-react), new frontend/src/components/system/{ScrambleText,SectionLabel,ThemeToggle,useTheme}.tsx (port from template code, adapt next-themes→hook), DESIGN.md (REWRITE: full new system — palette, type, borders, motion, verdict mapping, section-label pattern, do/don't).
- Keep existing app compiling: retain legacy token names as aliases where existing components reference them (verdict-pass/warn, ember, hairline...) mapped onto the new palette so T3/T4 can migrate incrementally without a broken intermediate state.
- Gates. Commit: `feat(design): brutalist design system tokens, fonts, primitives; DESIGN.md rewrite`

### Task T3: Marketing restyle (uses T2)
Files: frontend/src/pages/marketing/** rebuilt to the template: Navbar (bordered bar, theme toggle, Request Demo→"Open Dashboard"), Hero (pixel headline + WorkflowDiagram SVG adapted to AgentDiff pipeline + split-arrow CTA), FeatureGrid 2×2 bento (TerminalCard with AgentDiff log lines [agentdiff compare output flavored], DitherCard canvas, MetricsCard with TRUTHFUL product stats, StatusCard as provider/edge table—adapt to "capture shims status"), About (manifest/uptime→adapt: MANIFEST.md → METHODOLOGY excerpt, truthful stats grid), Pricing (REAL tiers: free/pro/enterprise from quota system), GlitchMarquee (provider ecosystem), Footer; docs pages restyled chrome (sidebar/typography to new system).
- Every border square; orange sparing; uppercase mono labels; section-label pattern with indices; framer-motion entrances w/ template ease.
- Gates + preview screenshots (light AND dark). Commit: `feat(marketing): brutalist landing — hero, bento, about, pricing, marquee, docs chrome`

### Task T4: Dashboard restyle (uses T2; parallel with T3, disjoint files)
Files: frontend/src/components/{Shell,Toaster,AgentGraph,nodes/*,attribution/*,overview/*,timeline/*}.tsx, frontend/src/pages/{ProjectsPage,ProjectPage,RunDetailPage}.tsx, frontend/src/sections/*.tsx.
- Restyle CHROME ONLY — zero functional changes: bordered-2 panels with header bars (`file.ext`-style labels), mono uppercase micro-labels, sharp corners, dot-grid page bg, verdict mapping per the locked decision, tables per template StatusCard style, buttons → split-arrow/solid mono style, modals → bordered squares, usage bars → template throughput-bar style, tabs → bordered segmented mono.
- All 41 vitest green; every page state must render (loading/error/empty preserved).
- Gates + preview screenshots of projects/project/run-detail (five tabs). Commit: `feat(dashboard): brutalist restyle of shell, lists, and five-view report`

### Task T5: Integration, retirement, hosting, finish
- Delete `landing/` after parity check (docs/privacy/terms/SEO all present in frontend). Replace deploy-landing.yml → deploy workflow for unified frontend (Pages) AND document Vercel path (vercel.json + envs) in docs/deploy-production.md ("Hosting the UI" section). Update README (single app), CHANGELOG entry. Update docker-compose dashboard service if its build context needs the new app (it builds frontend/ already — verify).
- Full gates: frontend build+test, engine pytest -q unchanged-green (sanity), docker dashboard image builds. Preview-verify one-link flow: `/` → Get started → sign-in wall → (if Clerk dev works) projects.
- Whole-branch review (opus) then finishing-a-development-branch.
- Commit: `chore(ui): retire landing app, one-link deploy config, docs`

Sequencing: T1 → T2 → (T3 ∥ T4) → T5.

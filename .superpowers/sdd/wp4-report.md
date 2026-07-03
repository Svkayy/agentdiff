# WP4 Dashboard — Implementation Report

**Date:** 2026-07-03
**Branch:** feat/report-ui

---

## Pages Built

| Route | Component | Status |
|-------|-----------|--------|
| `/` | `ProjectsPage` | Done |
| `/projects/:id` | `ProjectPage` (Runs / Setup / Slack tabs) | Done |
| `/runs/:id` | `RunDetailPage` | Done |
| Auth gate | `SignedIn`/`SignedOut` + `SignIn` | Done |
| Shell | Top bar, wordmark, Clerk UserButton, breadcrumb | Done |

---

## Design Decisions

**Light theme everywhere** (user-approved override of DESIGN.md dark default):
- Shell `#FAFAF8`, cards `#FFFFFF`, hairlines `#E6E3DD`, ink `#15181D`
- Agent graph plates use `dot-grid-light` (radial-gradient `#E6E3DD` dots) instead of dark canvas
- Ember `#FF4D2E` reserved exclusively for regression signals — stopped nodes, kind=drift badge outline, fail verdict badges

**Aceternity components** copied from `landing/src/components/aceternity/` into `frontend/src/components/aceternity/`:
- `Spotlight`, `BentoGrid`, `CardHoverEffect`, `TextGenerateEffect`, `Timeline`
- `useSkipEntrance` guard preserved — entrance animations skip to final state when `document.visibilityState === "hidden"` or `prefers-reduced-motion` is set. Bug was already fixed in landing; same guard copied verbatim.

**Agent graph (light SVG):** Adapted from `landing/src/components/GraphPlate.tsx`. Chose SVG over `@xyflow/react` per the "do not burn time" directive. Dynamic agents sourced from `run.config.agents`; falls back to 3 placeholder nodes if config is empty. Stopped agents derived by matching failing finding titles against agent names (prefix match).

**Router:** `react-router-dom` v7 added. `BrowserRouter` wraps entire app; `SignedIn`/`SignedOut` gates inside.

**Auto-refresh:** Runs tab polls every 15 s while any run has `status === "pending" | "processing"`. Interval cleared on cleanup.

**Reveal-once key modal:** Full key shown once in modal with copy button + "you won't see this again" warning. No persistence.

**Drift callout:** Rendered when `run.kind === "drift"` and all findings lack `cause_path` — ember-bordered callout per spec.

---

## Files Changed

### Backend (Step 0)
- `server/routes/reads.py` — add `kind`, `created_at`, `baseline_ref`, `candidate_ref`, `config` to `list_runs` / `get_run`
- `tests/server/test_reads.py` — assert new fields present

### Frontend (new/modified)
- `src/main.tsx` — Clerk guard, `MissingClerkConfig` card
- `src/App.tsx` — BrowserRouter, auth gate, routes
- `src/index.css` — light shell body color, `dot-grid-light`
- `src/lib/api.ts` — typed `fetchMe/fetchProjects/createProject/mintKey/listKeys/revokeKey/putSlackConfig`
- `src/lib/api.test.ts` — 8 new tests (11 total)
- `src/components/Shell.tsx` — top bar shell
- `src/components/aceternity/` — 5 components copied from landing
- `src/pages/ProjectsPage.tsx` — projects home
- `src/pages/ProjectPage.tsx` — project tabs
- `src/pages/RunDetailPage.tsx` — run detail + light SVG graph
- `DESIGN.md` — decisions log entry appended

---

## Test / Build Output

```
# Backend
pytest tests/server -q → 60 passed in 2.46s
ruff check server/ tests/server/ → All checks passed!

# Frontend
npx vitest run → 11 tests, 11 passed
tsc --noEmit → clean (no output)
npm run build → ✓ built in 998ms (897 kB gzipped 514 kB)
```

---

## Commits

| SHA | Subject |
|-----|---------|
| `825165c` | feat(server): expose kind, created_at, config in read endpoints |
| `e4b6454` | feat(frontend): api client, auth gate, shell, router, aceternity components |
| `95103bc` | feat(frontend): Projects, Project, and RunDetail pages with light theme |

---

## Self-Review

**What's solid:**
- TSC strict clean, vite build passes, all 11 vitest tests pass
- `useSkipEntrance` guard correctly reused — no entrance-animation regression
- Ember color reserved for regression signals only (no decorative use)
- Auto-refresh cleanup handled properly via `useEffect` return
- Reveal-once key modal pattern correct (no re-display)
- Cross-tenant isolation is backend concern, not duplicated in frontend

**Known gaps / concerns:**
- `fetchMe` calls `/v1/me` which doesn't exist in the current backend — used only for potential future consumption; not called in the UI yet. The test stubs fetch so it still passes.
- `listKeys` / `mintKey` / `revokeKey` call key endpoints (`/v1/projects/:id/keys`, `/v1/keys/:id`) that are not yet in the backend routes — Setup tab will get API 404s in production until those routes are added. The tab gracefully swallows the error and shows empty state.
- The agent graph dynamic layout uses a simple vertical stack. For agents with more complex DAG topology (branching), a proper layout algorithm would be needed. The fallback is functional and matches the landing GraphPlate pattern.
- `@types/react-router-dom` v5.3.3 was auto-installed as a peer type — react-router-dom v7 ships its own types, so this is redundant but harmless. Can be removed.
- No `vitest` for React components (no testing-library setup). Component-level tests would be the natural next investment.

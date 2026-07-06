# Design System — AgentDiff

> This document is LAW (see CLAUDE.md: "Always read DESIGN.md before making
> any visual or UI decisions"). It supersedes the prior "editorial data-viz /
> instrument" system in every particular below. T3 (marketing restyle) and
> T4 (dashboard restyle) build from this document.

## Product Context
- **What this is:** Behavioral regression testing for AI agent systems. The
  dashboard's hero is a before/after agent graph that shows when a
  sub-agent silently stopped firing after a code change.
- **Who it's for:** Startup AI engineers shipping agentic features.
- **Space/industry:** AI agent observability / eval tooling (peers:
  LangSmith, Langfuse, Braintrust, Arize). Differentiated by behavioral
  *diff* + causal attribution, not traces.
- **Project type:** One unified Vite SPA — public marketing routes
  (`/`, `/docs`, `/privacy`, `/terms`) plus a Clerk-gated dashboard
  (`/projects`, `/projects/:id`, `/runs/:id`).
- **Memorable thing:** "You can SEE the regression." The graph is built to
  be screenshotted and shared; the one agent that broke is the loudest
  thing on screen.

## Aesthetic Direction
- **Direction:** Brutalist / terminal-instrument ("SYS.INT"-derived). Every
  surface is a bordered rectangle — a plate, a card, a header bar — never a
  soft panel.
- **Decoration level:** intentional and sparse. 2px square borders
  everywhere, a faint dot-grid background texture, uppercase mono labels,
  zero-padded indices, occasional glitch/scramble/blink flourishes. No
  gradients, no drop shadows, no soft blobs, no rounded corners.
  Ornamentation communicates "instrumentation panel," not decoration for
  its own sake.
- **Mood:** Serious, technical, unmistakably a developer tool. The one
  signal color (orange) is reserved for regressions and calls-to-action —
  everything else is cream/black/gray so the signal reads instantly.
  Motion is quiet: entrances only, no idle looping animation except the
  handful of named brutalist flourishes below.
  Reference feel: an old CRT terminal crossed with a spec sheet — Braun/
  Rams instrument panels, not a SaaS landing page.

## Typography
- **Body / UI (`font-mono`):** JetBrains Mono — self-hosted via
  `@fontsource/jetbrains-mono` (weights 400/500/700). This is the default
  body font (`body { @apply font-mono }` in `frontend/src/index.css`).
  Virtually all brutalist UI text is mono: labels, buttons, nav, prose,
  numerals.
- **Display / pixel headline (`font-pixel`):** Silkscreen — self-hosted via
  `@fontsource/silkscreen` (weights 400/700). Use sparingly, for hero
  headline treatments or a handful of oversized display moments. **Font
  choice note:** the reference template's `font-pixel` maps to the `geist`
  npm package's Pixel Grid woff2 via Next's `next/font/local`. That API is
  Next-only and does not resolve under Vite (the package only exposes the
  pixel faces wrapped in a `next/font/local` call, not as directly
  importable asset paths through its public `exports`). Silkscreen is the
  documented fallback (per the locked architecture decision) and is a
  genuine bitmap/pixel Google Font, not a compromise substitute.
- **Legacy faces (kept, pre-T3/T4 components only):** Cabinet Grotesk
  (`font-display`) and Geist Variable (`font-sans`/`font-body`) remain
  available so old dashboard/marketing components that haven't been
  restyled yet keep rendering. New brutalist components should not
  introduce new usages of `font-display`/`font-sans`/`font-body` — use
  `font-mono` (or `font-pixel` for display moments) instead.
- **Case & tracking:** section labels, nav items, buttons, badges, and
  micro-copy are UPPERCASE with wide tracking (`tracking-[0.15em]` to
  `tracking-[0.2em]`), 10–11px. Headlines and body copy are normal case.
- **Scale:** headline 2–3rem (`text-2xl`–`text-4xl` for section H2s, larger
  for hero), body 0.75–0.875rem (`text-xs`/`text-sm`) is the brutalist
  default — most UI copy in the reference system runs small and dense.
  Line-height: tight for headlines, `leading-relaxed` for mono body copy.
  Tabular numerals (`font-variant-numeric: tabular-nums`, `.tnum`/`.tabular`
  utility classes) for any value that updates or aligns in a column.

## Color
Primary token set (HSL CSS custom properties, `frontend/src/index.css`,
`:root` = light / `.dark` = dark; `darkMode: "class"` in
`tailwind.config.js`):

| Token | Light (`:root`) | Dark (`.dark`) |
|---|---|---|
| `--background` | `43 23% 93%` (warm cream) | `0 0% 6%` (near-black) |
| `--foreground` | `0 0% 4%` (near-black ink) | `43 23% 93%` (cream) |
| `--card` | `43 23% 93%` | `0 0% 8%` |
| `--popover` | `43 23% 93%` | `0 0% 8%` |
| `--primary` | `0 0% 4%` | `43 23% 93%` |
| `--secondary` | `0 0% 90%` | `0 0% 14%` |
| `--muted` | `40 10% 85%` | `0 0% 15%` |
| `--muted-foreground` | `0 0% 40%` | `0 0% 60%` |
| `--accent` | `20 90% 45%` | `20 90% 50%` |
| `--destructive` | `0 84% 60%` | `0 84% 60%` |
| `--border` / `--input` | `0 0% 75%` | `0 0% 25%` |
| `--ring` | `0 0% 4%` | `43 23% 93%` |
| `--radius` | `0rem` | `0rem` |

- **Approach:** restrained cream/black/orange system. One signal color
  (`#ea580c`, the `--accent` family) carries the entire brand identity and
  every "this needs your attention" moment.
- **`#ea580c` usage rules:** the split-arrow CTA button's arrow chip,
  section-label blinking dot, scramble-price/scramble-stat highlights,
  pricing "RECOMMENDED" tag, verdict FAIL state, live-status indicator
  dots, glitch-marquee accents. Never used for large background fills or
  as a generic "brand" wash — it stays a small, sharp accent so it keeps
  reading as a signal rather than decoration.
- **Ink:** `hsl(var(--foreground))` — near-black on the light cream shell,
  cream on the dark shell.
- **Dot-grid background:** `.dot-grid-bg` (+ automatic `.dark .dot-grid-bg`
  variant) — a faint radial-gradient dot texture, 24px grid, used behind
  hero/section content for the "instrument panel" texture.
- **Verdict mapping (MUST stay distinguishable — locked decision):**
  - **pass** → foreground/neutral chip (no color signal; calm, "nothing to
    see here"). Legacy `verdict-pass`/`text-pass`/`bg-pass` still resolve
    to a distinguishable green (`--color-pass`) for pre-T4 dashboard code;
    T4 restyle should move pass chips to the neutral/foreground treatment
    described here.
  - **warn** → orange OUTLINE (border in `#ea580c`/accent, not a solid
    fill) — visually between "calm" and "signal."
  - **fail** → solid `#ea580c` — the loudest state on the page, matching
    the ember/signal reservation above.
  - Data-viz (graph nodes/edges, deltas) keeps these three states visually
    distinct within the cream/black/orange palette — never falls back to
    a rainbow chart palette.
- **Theme default:** light. No `prefers-color-scheme` / system detection —
  dark mode is opt-in only, toggled via `ThemeToggle` and persisted to
  `localStorage`.

### Legacy token aliases (kept for pre-T3/T4 code — do not delete)
Existing dashboard/marketing components reference an older palette. These
names are preserved and now resolve onto the tokens above via
`--color-*` CSS variables (see `frontend/src/index.css`) so nothing breaks
mid-migration:

| Legacy name | Old value | New resolution |
|---|---|---|
| `ember` | `#FF4D2E` | `#ea580c` (new signal orange) |
| `verdict-fail` | `#FF4D2E` | `#ea580c` |
| `verdict-warn` / `warn` / `text-warn` | `#E8A33D` | `#b45309` (warm amber-orange, outline family) |
| `verdict-pass` / `pass` / `text-pass` | `#3FB27F` | `#2f6b46` (calm distinguishable green — kept until T4 moves pass to neutral/foreground) |
| `ink` / `ink-dark` | `#15181D` | `#0a0a0a` (foreground on light) |
| `ink-light` | `#E8EBEF` | `#ede8dc` (foreground on dark canvas) |
| `shell` / `shell-bg` | `#FAFAF8` | `#ede4cf` (new cream background) |
| `shell-dark` | `#14161A` | `#0f0f0f` (new dark background) |
| `hairline` | `#E6E3DD` | `#bfbcb0` (border gray on cream) |
| `neutral-faint` / `faint` | `#8A929C` | `#999999` |
| `neutral-muted` | `#5B6470` | `#666666` |
| `canvas` | `#0E1116` | `#0f0f0f` |
| `node-fill` / `node` | `#1B2027` | `#1a1a1a` |
| `node-border` / `nodeborder` | `#2A313B` | `#3a3a3a` |
| `px-md`/`py-sm`/`gap-*`/`text-small`/`text-micro`/etc. | 8px-base spacing/type scale | unchanged — these are layout primitives, not palette, and stay as-is |

Dark-mode variants of every `--color-*` alias are defined under `.dark` in
`index.css` so legacy components also respond correctly to the theme
toggle.

## Borders, Radius & Surfaces
- **Border width:** 2px (`border-2`) is the default structural border for
  panels, cards, section dividers, and grid cells. 1px (`border`) is used
  only for hairline internal dividers (e.g. a divider inside a header bar).
- **Radius:** `0` everywhere. `--radius: 0rem`. Every corner is square. The
  one deliberate exception is the legacy `rounded-full` (status dots,
  small circular indicators) — round dots are fine, round rectangles are
  not.
- **No shadows, no gradients.** Depth and hierarchy come entirely from
  borders, background contrast, and spacing — never `box-shadow` (aside
  from the legacy, load-once `halo-glow`/`ember-pulse` treatment kept for
  pre-T4 code) and never `linear-gradient`/`radial-gradient` fills (the
  dot-grid's radial-gradient dots are the sole exception — that's texture,
  not a surface fill).
- **Header-bar card pattern:** every bordered "card" gets a thin header
  bar (`flex items-center justify-between px-5 py-3 border-b-2`) showing a
  `file.ext`-style label on the left (e.g. `MANIFEST.md`, `STATUS.log`,
  `agentdiff-compare.sh`) and a secondary meta value on the right (a
  version tag, a live badge, a zero-padded index). This is the
  "instrument nameplate" for every panel. In the dashboard this is also
  where verdict badges / traffic-light-style status dots belong (three
  small dots — pass/warn/fail — top-right of a card header, echoing
  terminal traffic lights, not literally red/yellow/green — use the
  verdict mapping above).

## Motion
- **Easing:** `[0.22, 1, 0.36, 1]` (a snappy ease-out) for essentially all
  entrance transitions — this is the one easing curve used throughout the
  brutalist system (framer-motion `transition.ease`).
- **Entrances:** content fades/slides/blurs in once, on scroll into view
  (`whileInView`, `viewport={{ once: true, margin: "-XXpx" }}`) — never
  replays. Common patterns:
  - Section labels: `initial={{ opacity: 0, x: -20 }}` → `x: 0`.
  - Body blocks / cards: `initial={{ opacity: 0, y: 16–30 }}` → `y: 0`,
    optionally with `filter: "blur(4–6px)"` → `blur(0px)` for a soft focus-in.
  - Staggered lists (feature grid, pricing features): index-based `delay`
    (e.g. `delay: i * 0.08–0.12`).
- **Brutalist flourishes (named, all in `frontend/src/index.css`):**
  - `.animate-glitch` (`@keyframes glitch`, 5s infinite) — brief
    hue-rotate/translate stutter, used sparingly on marquee logo blocks to
    sell the "signal noise" motif. Never on primary content.
  - `.animate-marquee` (`@keyframes marquee`, 30s linear infinite) — the
    provider-ecosystem logo strip's continuous horizontal scroll. The
    keyframes translate to `-50%`, so the strip MUST render its item list
    duplicated back-to-back (`[...ITEMS, ...ITEMS]`, `w-max`) — a single
    un-duplicated list produces a visible jump-cut when the loop restarts.
  - `.animate-blink` (`@keyframes blink`, 1s step-end infinite) — the
    small square "live" indicator dot used in section labels and status
    lines.
  - `ScrambleText` / scramble-price effects — a terminal-decode reveal
    (random chars resolving left-to-right into the real string) triggered
    once on scroll-into-view. Use for stat values, prices, and other
    "data materializing" moments — not for prose.
- **Hover/tap micro-interactions:** buttons and interactive chips use
  `whileHover={{ scale: 1.02–1.05 }}` / `whileTap={{ scale: 0.92–0.97 }}`,
  not color-only hover states.

## Patterns

### Section-label pattern
Every major section opens with a one-line label:

```
// SECTION: NAME  ─────────────────────────────  ●  004
```

Implemented as `frontend/src/components/system/SectionLabel.tsx`:
uppercase 10px mono, `tracking-[0.2em]`, `text-muted-foreground`, a
`flex-1 border-t border-border` divider filling the remaining width, an
optional blinking orange dot (`animate-blink`, `bg-[#ea580c]`), and the
section's 1-based index zero-padded to 3 digits (`004`). Entrance:
`x: -20 → 0`, once in view. Every top-level marketing section (and any
dashboard section adopting this system) should open with this component
rather than a bespoke heading.

### Split-arrow CTA pattern
Primary buttons are two visually distinct halves in one control: a small
solid `#ea580c` square containing an arrow icon (`lucide-react`
`ArrowRight`), flush against a larger flat-colored label region (usually
`bg-foreground text-background` or the inverse on a highlighted surface).
No rounded corners, no gap between the two halves — they read as one
bordered rectangle split in two. `whileHover`/`whileTap` scale, not a
color transition.

### Header-bar card pattern
See "Header-bar card pattern" under Borders/Surfaces above — the
`file.ext`-label + meta-value header bar is the standard top edge of every
bordered card/panel (terminal cards, metrics cards, pricing tiers, the
about-section manifest panel, dashboard report panels).

### Bento grid
Feature/overview grids are a single bordered rectangle (`border-2
border-foreground`) subdivided by internal 2px borders into 2×2 (or N×N)
cells — never separate cards with gaps. Each cell is its own
header-bar-card internally.

## Spacing
- **Base unit:** 8px (unchanged from the legacy system): `2xs(2) xs(4)
  sm(8) md(16) lg(24) xl(32) 2xl(48) 3xl(64)`.
- **Section padding:** `px-6 py-20 lg:px-12` is the standard marketing
  section wrapper (generous vertical rhythm, tight horizontal on mobile).
- **Density:** dashboard panels are denser than marketing sections — favor
  `px-5 py-3` header bars and `px-5 py-4/6` bodies.

## Layout
- **Max content width:** 1240px (`max-w-content`, unchanged).
- **Grids are borders, not gaps:** brutalist grids use `grid-cols-N` with
  `gap-0` and rely on `border-r-2`/`border-b-2` between cells, not
  Tailwind gap utilities, so every seam is a visible hairline/structural
  border rather than empty space.

## Theming Implementation
- `darkMode: "class"` in `tailwind.config.js` — dark mode is a `.dark`
  class on `<html>`, never a media query.
- `frontend/src/components/system/useTheme.ts` — reads/writes
  `localStorage` (`agentdiff-theme`), defaults to `"light"`, toggles the
  `dark` class on `document.documentElement`. No system-preference
  detection (locked decision — adapted from the reference template's
  `next-themes`, since this is a Vite SPA, not Next).
- `frontend/src/components/system/ThemeToggle.tsx` — Sun/Moon
  (`lucide-react`) icon swap via `framer-motion` `AnimatePresence`, a
  bordered square button, a placeholder square shown until the component
  mounts (avoids a theme-flash before `localStorage` is read).

## Do / Don't
**Do:**
- Use 2px square borders for every structural panel edge; `0` radius
  everywhere except status dots.
- Reserve `#ea580c` for signals: CTA arrow chips, fail verdicts,
  blinking/live indicators, highlighted-tier tags.
- Use uppercase mono labels with wide tracking for anything that isn't
  prose or a headline.
- Use the section-label pattern (`SectionLabel.tsx`) to open every major
  section.
- Use the one easing curve (`[0.22, 1, 0.36, 1]`) and trigger entrances
  once, on scroll into view.
- Keep verdict pass/warn/fail visually distinct at all times, in both
  themes.

**Don't:**
- Don't add rounded corners, drop shadows, or gradient fills to new
  brutalist components.
- Don't use `#ea580c` as a decorative background wash or "brand" tint —
  it must stay a sparse, sharp signal.
- Don't introduce new usages of the legacy `font-display`/`font-sans`/
  `font-body` (Cabinet Grotesk/Geist) faces — new work uses `font-mono`
  (body) / `font-pixel` (display, sparingly).
- Don't loop decorative motion beyond the four named flourishes
  (glitch/marquee/blink/scramble) — everything else animates in once.
- Don't collapse the pass/warn/fail distinction into a single color or a
  color-only difference that fails at a glance or without color vision.
- Don't delete legacy token names (`ink`, `hairline`, `ember`, `verdict-*`,
  spacing/type-scale utilities) even after a component is restyled onto
  the new system — other not-yet-migrated components still depend on them
  until the whole app is ported.

## Implementation Stack (unchanged)
- **Frontend:** Vite + React + TypeScript, one SPA (public marketing
  routes + Clerk-gated dashboard routes), graph via **React Flow** (custom
  node components for agent/tool, the signal-orange stopped state, the
  rate label).
- **Fonts:** `@fontsource/jetbrains-mono` (mono/body),
  `@fontsource/silkscreen` (pixel/display), both self-hosted — no CDN, no
  `next/font` (this is Vite, not Next).
- **Served by:** the Python CLI (`agentdiff dashboard --serve`) serves the
  built static assets (`vite build --config vite.cli.config.ts`, single-
  file via `vite-plugin-singlefile`); Vercel hosts the standard multi-file
  build (`vite build`) for the hosted one-link UI.
- **Data contract:** the existing `AgentGraph` model (nodes/edges/verdict/
  stopped/hunk) is the interface between the Python engine and the React
  app — no engine changes needed.

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-21 | Initial design system created | /design-consultation. Memorable thing: "you can SEE the regression." One ember signal color, editorial data-viz, graph-as-plate. |
| 2026-06-21 | Stack: Vite + React + React Flow | User chose Option C for the richest interactive graph; real layout engine + custom node components. |
| 2026-07-03 | Dashboard light theme (user-approved override of dark graph canvas); Aceternity motion components adopted | User directive during Tier 1-3 build |
| 2026-07-05 | Brutalist "SYS.INT"-derived rework replaces the editorial-instrument system | User-supplied reference template; T2 of the brutalist-ui plan. Cream/black/#ea580c palette, 2px square borders/0 radius, JetBrains Mono + Silkscreen, dot-grid bg, glitch/marquee/blink/scramble motion. Legacy tokens re-mapped (not deleted) for incremental T3/T4 migration. |

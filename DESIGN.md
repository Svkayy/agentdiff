# Design System — AgentDiff

## Product Context
- **What this is:** Behavioral regression testing for AI agent systems. The dashboard's hero is a before/after agent graph that shows when a sub-agent silently stopped firing after a code change.
- **Who it's for:** Startup AI engineers shipping agentic features.
- **Space/industry:** AI agent observability / eval tooling (peers: LangSmith, Langfuse, Braintrust, Arize). Differentiated by behavioral *diff* + causal attribution, not traces.
- **Project type:** Local-first developer dashboard (served by the CLI).
- **Memorable thing:** "You can SEE the regression." The graph is built to be screenshotted and shared; the one agent that broke is the loudest thing on screen.

## Aesthetic Direction
- **Direction:** Editorial data-viz / "instrument." The agent graph is a framed plate, not a generic dashboard panel.
- **Decoration level:** intentional — hairline borders, a subtle dot/grid texture on the graph canvas, no gradients, no blobs.
- **Mood:** Serious instrumentation that is also striking. Quiet everywhere so the single regression signal is unmistakable.
- **Reference feel:** Observable / data-journalism graphics meet Linear-grade product restraint.

## Typography
- **Display/Hero:** Cabinet Grotesk — confident, distinctive headline grotesk (Fontshare). Used for the plate title and section headers.
- **Body / UI:** Geist — clean, technical, developer-native (Google Fonts / Vercel). Labels, prose, controls.
- **Data / rates:** Geist Mono **or** JetBrains Mono with `font-variant-numeric: tabular-nums` — precise numerals that do not jitter as values change.
- **Code / diff:** JetBrains Mono — the attributed hunk panel.
- **Loading:** Cabinet Grotesk via Fontshare (`api.fontshare.com`); Geist + JetBrains Mono via Google Fonts. Self-host into the frontend bundle for offline use.
- **Scale (rem, 1rem=16px):** display 2.0 / h1 1.5 / h2 1.25 / body 1.0 / small 0.875 / micro 0.75. Line-height: 1.2 headings, 1.5 body.

## Color
- **Approach:** restrained — one signal color is the entire brand identity.
- **Signal (ember):** `#FF4D2E` — used **only** for a regression / stopped-firing node and its halo. Never decorative. This reservation is what makes it ownable.
- **Ink (text):** `#15181D` on light; `#E8EBEF` on the dark graph canvas.
- **Graph canvas:** `#0E1116` (deep near-black) — nodes pop against it.
- **Surfaces (light shell):** background `#FAFAF8` (warm off-white), card `#FFFFFF`, hairline border `#E6E3DD`.
- **Neutrals:** slate ramp for calm nodes/edges — `#5B6470` (muted), `#8A929C` (faint), node fill on canvas `#1B2027` with border `#2A313B`.
- **Semantic verdicts:** pass `#3FB27F` (calm green), warn `#E8A33D` (restrained amber), fail/stopped = ember `#FF4D2E`.
- **Dark mode:** the graph plate is already dark; a full dark shell reduces surface saturation ~15% and swaps the warm off-white for `#14161A`.

## Spacing
- **Base unit:** 8px.
- **Density:** comfortable — the graph needs negative space to read as a "plate."
- **Scale:** 2xs(2) xs(4) sm(8) md(16) lg(24) xl(32) 2xl(48) 3xl(64).

## Layout
- **Approach:** hybrid, graph-forward. The graph plate dominates the top; an attribution rail sits to its right; quiet metric chips below.
- **Grid:** graph plate spans full content width; detail rail ~ 1/3 on desktop, stacks under the graph on narrow screens.
- **Max content width:** 1240px.
- **Border radius:** sm 6px (chips, inputs), md 10px (cards, nodes), lg 14px (the plate), full 9999px (status dots).

## Motion
- **Approach:** intentional. Nodes fade-and-scale in (short, ease-out, staggered), edges draw in, and the stopped node gets **one** attention pulse on load (a single ember halo expand-and-settle). After load, the surface is still.
- **Easing:** enter ease-out, exit ease-in, move ease-in-out.
- **Duration:** micro 80ms / short 200ms / medium 320ms / long 600ms (the one-time stopped-node pulse).

## Implementation Stack (decided)
- **Frontend:** Vite + React + TypeScript, graph via **React Flow** (custom node components for agent/tool, the ember stopped state, the rate label).
- **Served by:** the Python CLI (`agentdiff dashboard --serve`) serves the built static assets; the run data (graph model JSON from `graph_model.build`) is embedded into the page or read from a sibling JSON.
- **Data contract:** the existing `AgentGraph` model (nodes/edges/verdict/stopped/hunk) is the interface between the Python engine and the React app — no engine changes needed.

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-21 | Initial design system created | /design-consultation. Memorable thing: "you can SEE the regression." One ember signal color, editorial data-viz, graph-as-plate. |
| 2026-06-21 | Stack: Vite + React + React Flow | User chose Option C for the richest interactive graph; real layout engine + custom node components. |

/** @type {import('tailwindcss').Config} */
// Tokens from DESIGN.md — AgentDiff brutalist ("SYS.INT"-derived) design
// system (T2). Primary palette is the HSL var set in src/index.css
// (background/foreground/card/muted/accent/border/ring, radius 0). Legacy
// flat keys (ink, shell, hairline, ember, verdict-*, neutral-*, ...) are kept
// and re-mapped onto the new palette so existing components keep compiling.
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // ── LEGACY KEYS (T2 — re-mapped onto the brutalist palette) ────────────
      // These names are kept verbatim (not deleted, not renamed) so every
      // pre-existing dashboard/marketing component keeps compiling. Their
      // VALUES now come from the `--color-*` CSS vars defined in index.css
      // (:root + .dark), which are themselves derived from the new
      // cream/black/orange system. See t2-ui-report.md for the full
      // legacy → new mapping table.
      colors: {
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        "primary-dark": "#38bdf8",
        surface: "hsl(var(--card))",
        "surface-muted": "hsl(var(--muted))",
        "text-main": "hsl(var(--foreground))",
        "text-muted": "hsl(var(--muted-foreground))",

        // ── Signal color: was #FF4D2E (ember/red-orange) → now the
        // brutalist signal orange #ea580c (--color-ember). ────────────────
        ember: "var(--color-ember)",

        // ── Verdicts — pass/warn/fail must stay visually distinguishable.
        // pass: calm green (kept, distinguishable from the orange family);
        // warn: warm amber-orange (outline-ish, distinct from solid fail);
        // fail: solid signal orange (= ember). ─────────────────────────────
        verdict: {
          pass: "var(--color-pass)",
          warn: "var(--color-warn)",
          fail: "var(--color-ember)",
        },

        // ── ink (text) → foreground family. DEFAULT/dark = ink on light
        // shell; light = ink on the dark graph canvas. ─────────────────────
        ink: {
          DEFAULT: "var(--color-ink-dark)",
          dark: "var(--color-ink-dark)",
          light: "var(--color-ink-light)",
        },

        // ── Graph canvas — dark surface family (independent of the
        // light/dark theme toggle; the graph plate is always dark). ───────
        canvas: "var(--color-canvas)",
        "node-fill": "var(--color-node-fill)",
        "node-border": "var(--color-node-border)",
        node: "var(--color-node-fill)",
        nodeborder: "var(--color-node-border)",
        canvastext: "var(--color-ink-light)",

        // ── shell → background family (was #FAFAF8/#14161A). ───────────────
        shell: {
          DEFAULT: "var(--color-shell-bg)",
          bg: "var(--color-shell-bg)",
          card: "hsl(var(--card))",
          dark: "var(--color-shell-dark)",
        },
        hairline: "var(--color-hairline)",
        faint: "var(--color-neutral-faint)",
        pass: "var(--color-pass)",
        warn: "var(--color-warn)",

        // ── neutrals → muted-foreground family. ────────────────────────────
        neutral: {
          muted: "var(--color-neutral-muted)",
          faint: "var(--color-neutral-faint)",
        },

        // ── Brutalist design-system colors (T2) — CSS-variable-backed,
        // HSL token set ported from the reference template. These are now
        // the PRIMARY palette; legacy flat hex keys above remain as aliases
        // so pre-T3/T4 components keep compiling and looking coherent.
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        chart: {
          "1": "hsl(var(--chart-1))",
          "2": "hsl(var(--chart-2))",
          "3": "hsl(var(--chart-3))",
          "4": "hsl(var(--chart-4))",
          "5": "hsl(var(--chart-5))",
        },
      },

      // Marketing content width (ported from the landing app).
      maxWidth: {
        content: "1240px",
      },

      transitionTimingFunction: {
        // Landing entrance easing.
        enter: "cubic-bezier(0.16, 1, 0.3, 1)",
      },

      // ── Brutalist border radii (T2) — 0-based scale, sharp/square by
      // default. `DEFAULT`/`lg`/`md`/`sm` derive from `--radius` (0rem) per
      // the reference template. Legacy `full` (status dots) is kept as the
      // one exception — fully-round dots/pills still need `rounded-full`.
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 2px)",
        full: "9999px", // status dots (legacy — intentionally exempt from 0-radius)
        DEFAULT: "var(--radius)",
      },

      // ── Brutalist font families (T2) ──────────────────────────────────────
      fontFamily: {
        // Body / UI mono — JetBrains Mono (self-hosted via
        // @fontsource/jetbrains-mono). This is now the default body font
        // (see `body { @apply font-mono }` in index.css).
        mono: [
          '"JetBrains Mono"',
          "ui-monospace",
          "monospace",
        ],
        // Display / pixel headline face — Silkscreen (self-hosted via
        // @fontsource/silkscreen). See index.css header comment for why
        // Silkscreen was chosen over the `geist` package's pixel woff2s
        // (those are wrapped in next/font/local and don't resolve under Vite).
        pixel: [
          '"Silkscreen"',
          '"JetBrains Mono"',
          "monospace",
        ],
        // ── Legacy display/sans/body — kept for pre-T3/T4 components ───────
        // Display / hero — Cabinet Grotesk (self-hosted TTF); fallback to Geist
        display: [
          '"Cabinet Grotesk"',
          '"Geist Variable"',
          '"Geist"',
          "system-ui",
          "sans-serif",
        ],
        // Body / UI — Geist (self-hosted via @fontsource-variable/geist)
        sans: [
          '"Geist Variable"',
          '"Geist"',
          "system-ui",
          "sans-serif",
        ],
        // Marketing components use `font-body` for the same body stack.
        body: [
          '"Geist Variable"',
          '"Geist"',
          "system-ui",
          "sans-serif",
        ],
      },

      // ── DESIGN.md spacing (8px base) ─────────────────────────────────────
      spacing: {
        "2xs": "2px",
        xs: "4px",
        sm: "8px",
        md: "16px",
        lg: "24px",
        xl: "32px",
        "2xl": "48px",
        "3xl": "64px",
      },

      // ── Typography scale (rem, 1rem=16px per DESIGN.md) ──────────────────
      fontSize: {
        display: ["2rem", { lineHeight: "1.2" }],
        h1: ["1.5rem", { lineHeight: "1.2" }],
        h2: ["1.25rem", { lineHeight: "1.2" }],
        body: ["1rem", { lineHeight: "1.5" }],
        small: ["0.875rem", { lineHeight: "1.5" }],
        micro: ["0.75rem", { lineHeight: "1.5" }],
      },

      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        // DESIGN.md: one ember halo pulse on load for the stopped node
        "ember-pulse": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(234,88,12,0)" },
          "50%": { boxShadow: "0 0 0 12px rgba(234,88,12,0.25)" },
        },
      },
      animation: {
        "fade-in": "fade-in 200ms ease-out both",
        "ember-pulse": "ember-pulse 600ms ease-out 1",
      },
    },
  },
  plugins: [],
};

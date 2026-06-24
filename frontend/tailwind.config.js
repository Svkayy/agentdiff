/** @type {import('tailwindcss').Config} */
// Tokens from DESIGN.md — AgentDiff design system.
// Extends the existing keys so current components keep compiling.
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // ── Legacy keys (keep existing components compiling) ──────────────────
      colors: {
        // Legacy palette (kept for backward-compat)
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        "primary-dark": "#38bdf8",
        surface: "hsl(var(--card))",
        "surface-muted": "hsl(var(--muted))",
        "text-main": "hsl(var(--foreground))",
        "text-muted": "hsl(var(--muted-foreground))",

        // ── DESIGN.md signal ──────────────────────────────────────────────
        ember: "#FF4D2E",

        // ── DESIGN.md verdicts ────────────────────────────────────────────
        verdict: {
          pass: "#3FB27F",
          warn: "#E8A33D",
          fail: "#FF4D2E", // = ember
        },

        // ── DESIGN.md ink (text) ──────────────────────────────────────────
        ink: {
          dark: "#15181D",   // on light backgrounds
          light: "#E8EBEF",  // on dark graph canvas
        },

        // ── DESIGN.md graph canvas ────────────────────────────────────────
        canvas: "#0E1116",
        "node-fill": "#1B2027",
        "node-border": "#2A313B",

        // ── DESIGN.md surfaces (light shell) ─────────────────────────────
        shell: {
          bg: "#FAFAF8",       // warm off-white
          card: "#FFFFFF",
          dark: "#14161A",     // dark shell
        },
        hairline: "#E6E3DD",

        // ── DESIGN.md neutrals ────────────────────────────────────────────
        neutral: {
          muted: "#5B6470",
          faint: "#8A929C",
        },

        // ── shadcn/ui CSS-variable-backed colors ──────────────────────────
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

      // ── DESIGN.md border radii ────────────────────────────────────────────
      borderRadius: {
        sm: "6px",   // chips, inputs
        md: "10px",  // cards, nodes
        lg: "14px",  // the plate
        full: "9999px", // status dots
        // Keep shadcn defaults (CSS var-backed)
        DEFAULT: "var(--radius)",
      },

      // ── DESIGN.md font families ───────────────────────────────────────────
      fontFamily: {
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
        // Data / code — JetBrains Mono (self-hosted via @fontsource/jetbrains-mono)
        mono: [
          '"JetBrains Mono"',
          "ui-monospace",
          "monospace",
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
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(255,77,46,0)" },
          "50%": { boxShadow: "0 0 0 12px rgba(255,77,46,0.25)" },
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

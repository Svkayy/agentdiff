/** @type {import('tailwindcss').Config} */
// Tokens ported from the Stitch "Glacier Light" export — a light glassmorphism
// theme: sky-blue for healthy flow, ember reserved for the regression signal.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#7dd3fc",
        "primary-dark": "#38bdf8",
        ember: "#FF4D2E",
        surface: "#ffffff",
        "surface-muted": "#f1f5f9",
        "text-main": "#0f172a",
        "text-muted": "#64748b",
        border: "#e2e8f0",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 200ms ease-out both",
      },
    },
  },
  plugins: [],
};

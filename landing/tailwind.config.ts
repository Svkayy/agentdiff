import type { Config } from "tailwindcss";

// Palette is bound to DESIGN.md — do not add colors outside this ramp.
// Ember (#FF4D2E) is reserved for the regression signal only.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        shell: "#FAFAF8",
        card: "#FFFFFF",
        hairline: "#E6E3DD",
        ink: "#15181D",
        muted: "#5B6470",
        faint: "#8A929C",
        canvas: "#0E1116",
        node: "#1B2027",
        nodeborder: "#2A313B",
        canvastext: "#E8EBEF",
        pass: "#3FB27F",
        warn: "#E8A33D",
        ember: "#FF4D2E",
      },
      fontFamily: {
        display: ["'Cabinet Grotesk'", "'Geist Variable'", "system-ui", "sans-serif"],
        body: ["'Geist Variable'", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      maxWidth: {
        content: "1240px",
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "14px",
      },
      transitionTimingFunction: {
        enter: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
} satisfies Config;

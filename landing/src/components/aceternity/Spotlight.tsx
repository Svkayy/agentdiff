import { motion } from "framer-motion";
import { cn, useSkipEntrance } from "@/lib/utils";

/**
 * Aceternity "Spotlight" pattern, restrained for the AgentDiff design system:
 * instead of a colorful gradient beam, a single soft radial ink wash fades in
 * behind the hero. No hue, no glow — just tonal depth on the warm off-white
 * shell. Renders once, then stays still.
 */
export function Spotlight({ className }: { className?: string }) {
  const skip = useSkipEntrance();
  return (
    <motion.svg
      aria-hidden="true"
      initial={skip ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className={cn("pointer-events-none absolute -z-0 select-none", className)}
      viewBox="0 0 1400 800"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <radialGradient id="ad-ink-wash" cx="50%" cy="38%" r="62%">
          <stop offset="0%" stopColor="#15181D" stopOpacity="0.045" />
          <stop offset="55%" stopColor="#15181D" stopOpacity="0.02" />
          <stop offset="100%" stopColor="#15181D" stopOpacity="0" />
        </radialGradient>
      </defs>
      <ellipse cx="700" cy="300" rx="720" ry="420" fill="url(#ad-ink-wash)" />
    </motion.svg>
  );
}

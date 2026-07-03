/**
 * SectionReveal — Aceternity-style staggered entrance, tuned to DESIGN.md
 * motion: enter ease-out, short/medium durations, still after load. Sections
 * fade-and-rise once when they mount; switching sections re-triggers via key.
 */
import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { useSkipEntrance } from "@/lib/utils";

const EASE_OUT = [0.16, 1, 0.3, 1] as const;

export function SectionReveal({
  children,
  sectionKey,
}: {
  children: ReactNode;
  sectionKey: string;
}) {
  const skip = useSkipEntrance();
  return (
    <motion.div
      key={sectionKey}
      initial={skip ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: EASE_OUT }}
    >
      {children}
    </motion.div>
  );
}

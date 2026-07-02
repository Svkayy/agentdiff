import type { ReactNode } from "react";
import { motion } from "framer-motion";

export interface TimelineEntry {
  step: string;
  title: string;
  content: ReactNode;
}

/**
 * Aceternity "Timeline" pattern, restyled to the instrument aesthetic: a
 * vertical hairline rail with numbered mono step markers. Entries fade-and-
 * rise in on scroll (short, ease-out, staggered) and are still afterwards.
 */
export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <ol className="relative ml-1 border-l border-hairline">
      {entries.map((entry, i) => (
        <motion.li
          key={entry.step}
          initial={{ y: 12 }}
          whileInView={{ y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.32, ease: "easeOut", delay: 0.05 }}
          className="relative pb-12 pl-8 last:pb-0 md:pl-12"
        >
          <span
            aria-hidden="true"
            className="absolute -left-[15px] top-0 grid h-[30px] w-[30px] place-items-center rounded-full border border-hairline bg-card font-mono text-[11px] font-medium text-muted"
          >
            {String(i + 1).padStart(2, "0")}
          </span>
          <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-faint">
            {entry.step}
          </div>
          <h3 className="mt-1.5 font-display text-2xl font-bold leading-tight text-ink">
            {entry.title}
          </h3>
          <div className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted">
            {entry.content}
          </div>
        </motion.li>
      ))}
    </ol>
  );
}

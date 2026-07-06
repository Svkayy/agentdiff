import { motion } from "framer-motion";

const ease = [0.22, 1, 0.36, 1] as const;

export interface SectionLabelProps {
  /** Section name, e.g. "ABOUT_AGENTDIFF" — rendered as `// SECTION: NAME`. */
  label: string;
  /** 1-based section index, rendered zero-padded to 3 digits (e.g. 4 -> "004"). */
  index: number;
  /** Show the blinking orange dot next to the index (default true). */
  blink?: boolean;
  className?: string;
}

/**
 * Brutalist section-label pattern — ported from the repeated block seen in
 * the reference template's feature-grid.tsx / about-section.tsx:
 *
 *   // SECTION: NAME  ────────────────────────  ●  004
 *
 * Uppercase mono micro-label, a flex-1 hairline divider, an optional
 * blinking signal-orange dot, and a zero-padded section index. Entrance:
 * fades + slides in from x:-20 once, in view.
 */
export function SectionLabel({ label, index, blink = true, className }: SectionLabelProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.5, ease }}
      className={`flex items-center gap-4 mb-8 ${className ?? ""}`}
    >
      <span className="text-[11px] tracking-[0.2em] uppercase text-muted-foreground font-mono">
        {`// SECTION: ${label}`}
      </span>
      <div className="flex-1 border-t border-border" />
      {blink && (
        <span className="inline-block h-2 w-2 bg-[#ea580c] animate-blink" aria-hidden="true" />
      )}
      <span className="text-[11px] tracking-[0.2em] uppercase text-muted-foreground font-mono">
        {String(index).padStart(3, "0")}
      </span>
    </motion.div>
  );
}

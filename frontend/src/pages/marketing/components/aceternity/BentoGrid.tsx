import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { cn, useSkipEntrance } from "@/lib/utils";

/**
 * Aceternity "Bento Grid" pattern, restyled: white cards, hairline borders,
 * radius-md, no gradients or glass. Cards fade-and-rise in on scroll with a
 * short ease-out stagger, then stay still.
 */
export function BentoGrid({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("grid grid-cols-1 gap-4 md:grid-cols-3", className)}>
      {children}
    </div>
  );
}

export function BentoGridItem({
  className,
  title,
  kicker,
  description,
  header,
  index = 0,
}: {
  className?: string;
  title: string;
  kicker: string;
  description: string;
  header?: ReactNode;
  index?: number;
}) {
  const skip = useSkipEntrance();
  return (
    <motion.article
      initial={skip ? false : { y: 12 }}
      whileInView={{ y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.32, ease: "easeOut", delay: (index % 3) * 0.07 }}
      className={cn(
        "group flex flex-col rounded-md border border-hairline bg-card p-6",
        "transition-shadow duration-200 hover:shadow-[0_1px_0_#E6E3DD,0_12px_32px_rgba(21,24,29,0.06)]",
        className,
      )}
    >
      {header ? <div className="mb-5">{header}</div> : null}
      <div className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-faint">
        {kicker}
      </div>
      <h3 className="mt-2 font-display text-xl font-bold leading-tight text-ink">
        {title}
      </h3>
      <p className="mt-2 text-[15px] leading-relaxed text-muted">{description}</p>
    </motion.article>
  );
}

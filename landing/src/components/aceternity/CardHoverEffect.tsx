import { useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface HoverCard {
  id: string;
  title: string;
  description: string;
  body?: ReactNode;
}

/**
 * Aceternity "Card Hover Effect" pattern, restyled: the shared highlight that
 * follows the pointer between cards is a flat warm-neutral slab (no gradient,
 * no glow) behind white hairline cards.
 */
export function CardHoverEffect({
  items,
  className,
}: {
  items: HoverCard[];
  className?: string;
}) {
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <div className={cn("grid grid-cols-1 gap-4 md:grid-cols-3", className)}>
      {items.map((item, index) => (
        <motion.div
          key={item.id}
          initial={{ y: 12 }}
          whileInView={{ y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.32, ease: "easeOut", delay: index * 0.07 }}
          className="relative"
          onMouseEnter={() => setHovered(item.id)}
          onMouseLeave={() => setHovered(null)}
        >
          <AnimatePresence>
            {hovered === item.id && (
              <motion.span
                layoutId="card-hover-slab"
                className="absolute -inset-1.5 rounded-lg bg-[#EFEDE8]"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: 0.2, ease: "easeOut" } }}
                exit={{ opacity: 0, transition: { duration: 0.2, ease: "easeIn" } }}
              />
            )}
          </AnimatePresence>
          <div className="relative flex h-full flex-col rounded-md border border-hairline bg-card p-6">
            <h3 className="font-display text-lg font-bold leading-tight text-ink">
              {item.title}
            </h3>
            <p className="mt-2 text-[14px] leading-relaxed text-muted">
              {item.description}
            </p>
            {item.body ? <div className="mt-4">{item.body}</div> : null}
          </div>
        </motion.div>
      ))}
    </div>
  );
}

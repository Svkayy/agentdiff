import { motion } from "framer-motion";
import { SectionLabel } from "@/components/system/SectionLabel";
import { TerminalCard } from "./bento/TerminalCard";
import { DitherCard } from "./bento/DitherCard";
import { MetricsCard } from "./bento/MetricsCard";
import { StatusCard } from "./bento/StatusCard";

const ease = [0.22, 1, 0.36, 1] as const;

const cardVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.1, duration: 0.6, ease },
  }),
};

/**
 * 2×2 bento feature grid — ported from the template's `feature-grid.tsx`.
 * One bordered rectangle subdivided by 2px seams into four instrument cards.
 */
export function FeatureGrid() {
  return (
    <section className="w-full px-6 py-20 lg:px-12">
      <SectionLabel label="RAW_DATA" index={1} />

      <motion.div
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-60px" }}
        className="grid grid-cols-1 md:grid-cols-2 border-2 border-foreground"
      >
        <motion.div
          custom={0}
          variants={cardVariants}
          className="border-b-2 md:border-b-0 md:border-r-2 border-foreground min-h-[280px]"
        >
          <TerminalCard />
        </motion.div>

        <motion.div
          custom={1}
          variants={cardVariants}
          className="border-b-2 md:border-b-0 border-foreground min-h-[280px]"
        >
          <DitherCard />
        </motion.div>

        <motion.div
          custom={2}
          variants={cardVariants}
          className="border-t-2 md:border-r-2 border-foreground min-h-[280px]"
        >
          <MetricsCard />
        </motion.div>

        <motion.div custom={3} variants={cardVariants} className="border-t-2 border-foreground min-h-[280px]">
          <StatusCard />
        </motion.div>
      </motion.div>
    </section>
  );
}

import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { motion } from "framer-motion";
import { PUBLIC_SECONDARY_CTA } from "@/lib/publicCtas";
import { WorkflowDiagram } from "./WorkflowDiagram";

const ease = [0.22, 1, 0.36, 1] as const;

/**
 * Brutalist hero — ported from the reference template's `hero-section.tsx`.
 * Pixel headline split around the central WorkflowDiagram, a truthful
 * AgentDiff sub-headline, and public CTAs.
 */
export function HeroSection() {
  return (
    <section className="relative w-full px-12 pt-6 pb-12 lg:px-24 lg:pt-10 lg:pb-16">
      <div className="flex flex-col items-center text-center">
        {/* Top headline */}
        <motion.h1
          initial={{ opacity: 0, y: 30, filter: "blur(8px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.7, ease }}
          className="font-pixel text-3xl sm:text-5xl lg:text-6xl xl:text-7xl tracking-tight text-foreground mb-2 select-none"
        >
          CAPTURE. COMPARE.
        </motion.h1>

        {/* Central Workflow Diagram */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6, delay: 0.15, ease }}
          className="w-full max-w-4xl my-4 lg:my-6"
        >
          <WorkflowDiagram />
        </motion.div>

        {/* Bottom headline */}
        <motion.h1
          initial={{ opacity: 0, y: 30, filter: "blur(8px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.7, delay: 0.25, ease }}
          className="font-pixel text-3xl sm:text-5xl lg:text-6xl xl:text-7xl tracking-tight text-foreground mb-4 select-none"
        >
          ATTRIBUTE.
        </motion.h1>

        {/* Sub-headline — truthful AgentDiff pitch */}
        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.45, ease }}
          className="text-sm lg:text-base text-foreground/75 max-w-xl mb-6 leading-relaxed font-mono"
        >
          Behavioral regression testing for AI agent systems. AgentDiff captures
          your agent&apos;s runs, compares baseline against candidate with
          deterministic statistics, and attributes each regression to the commit
          that caused it. Any provider, any framework — none required.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.6, ease }}
          className="flex flex-wrap items-center justify-center gap-3"
        >
          <Link to="/demo">
            <motion.span
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              className="group inline-flex items-center gap-0 bg-foreground text-background text-sm font-mono tracking-wider uppercase"
            >
              <span className="flex items-center justify-center w-10 h-10 bg-[#ea580c]">
                <ArrowRight size={16} strokeWidth={2} className="text-background" />
              </span>
              <span className="px-5 py-2.5">View Demo</span>
            </motion.span>
          </Link>
          <Link
            to={PUBLIC_SECONDARY_CTA.path}
            className="inline-flex h-10 items-center border-2 border-foreground bg-background px-5 font-mono text-sm uppercase tracking-wider text-foreground transition-colors hover:bg-foreground hover:text-background"
          >
            {PUBLIC_SECONDARY_CTA.label}
          </Link>
        </motion.div>
      </div>
    </section>
  );
}

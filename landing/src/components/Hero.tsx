import { useCallback, useState } from "react";
import { motion } from "framer-motion";
import { Check, Copy, Star } from "lucide-react";
import { useSkipEntrance } from "@/lib/utils";
import { Spotlight } from "./aceternity/Spotlight";
import { TextGenerateEffect } from "./aceternity/TextGenerateEffect";
import { GraphPlate } from "./GraphPlate";

const INSTALL_CMD = "pip install agentdiff";

function InstallButton() {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(() => {
    void navigator.clipboard.writeText(INSTALL_CMD).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    });
  }, []);

  return (
    <button
      type="button"
      onClick={copy}
      aria-label="Copy pip install agentdiff to clipboard"
      className="inline-flex h-11 items-center gap-3 rounded-sm border border-ink bg-ink px-4 font-mono text-sm text-shell transition-colors duration-200 hover:bg-[#22262D]"
    >
      <span aria-hidden="true" className="text-faint">
        $
      </span>
      {INSTALL_CMD}
      {copied ? (
        <Check className="h-4 w-4 text-pass" aria-hidden="true" />
      ) : (
        <Copy className="h-4 w-4 text-faint" aria-hidden="true" />
      )}
    </button>
  );
}

export function Hero() {
  const skip = useSkipEntrance();
  return (
    <section id="top" className="relative overflow-hidden border-b border-hairline">
      <Spotlight className="left-1/2 top-0 w-[140%] max-w-none -translate-x-1/2" />
      <div className="relative mx-auto grid max-w-content gap-12 px-5 pb-20 pt-16 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:pt-24">
        <div>
          <motion.p
            initial={skip ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.32, ease: "easeOut" }}
            className="font-mono text-[12px] uppercase tracking-[0.16em] text-muted"
          >
            Behavioral CI gate for AI agents
          </motion.p>
          <motion.h1
            initial={skip ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.32, ease: "easeOut", delay: 0.06 }}
            className="mt-4 max-w-xl font-display text-4xl font-extrabold leading-[1.05] tracking-tight text-ink sm:text-5xl"
          >
            Catch the agent regressions your evals can&rsquo;t see.
          </motion.h1>
          <TextGenerateEffect
            words="Your eval suite says PASS. Your agent quietly stopped calling the fact-checker. AgentDiff catches what output evals miss — and names the commit."
            delay={0.35}
            className="mt-5 max-w-xl text-lg leading-relaxed text-muted"
          />
          <motion.div
            initial={skip ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.32, ease: "easeOut", delay: 0.5 }}
            className="mt-8 flex flex-wrap items-center gap-3"
          >
            <InstallButton />
            <a
              href="https://github.com/sandeepvinay/agentdiff"
              className="inline-flex h-11 items-center gap-2 rounded-sm border border-hairline bg-card px-4 text-sm font-medium text-ink transition-colors duration-200 hover:border-faint"
            >
              <Star className="h-4 w-4" aria-hidden="true" />
              Star on GitHub
            </a>
          </motion.div>
          <motion.p
            initial={skip ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.32, ease: "easeOut", delay: 0.65 }}
            className="mt-6 font-mono text-[12px] text-faint"
          >
            Any LLM provider · any framework · none required
          </motion.p>
        </div>
        <GraphPlate />
      </div>
    </section>
  );
}

import { motion } from "framer-motion";
import { SectionLabel } from "@/components/system/SectionLabel";

// Providers / frameworks AgentDiff actually supports (8 provider parsers +
// framework adapters + capture shims across the ecosystem).
const PROVIDERS = [
  "OPENAI",
  "ANTHROPIC",
  "GOOGLE",
  "MISTRAL",
  "BEDROCK",
  "COHERE",
  "AZURE",
  "OLLAMA",
  "LANGGRAPH",
  "CREWAI",
];

function LogoBlock({ name, glitch }: { name: string; glitch: boolean }) {
  return (
    <div
      className={`flex items-center justify-center px-8 py-4 border-r-2 border-foreground shrink-0 ${
        glitch ? "animate-glitch" : ""
      }`}
    >
      <span className="text-sm font-mono tracking-[0.15em] uppercase text-foreground whitespace-nowrap">
        {name}
      </span>
    </div>
  );
}

/**
 * Provider-ecosystem marquee — ported from the template's `glitch-marquee.tsx`.
 * The item list is duplicated back-to-back (the `marquee` keyframes translate
 * to -50%, so a single list would jump-cut on loop).
 */
export function GlitchMarquee() {
  const glitchIndices = [2, 6];

  return (
    <section className="w-full py-16 px-6 lg:px-12">
      <SectionLabel label="ECOSYSTEM" index={3} />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-40px" }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="overflow-hidden border-2 border-foreground"
      >
        <div className="flex animate-marquee" style={{ width: "max-content" }}>
          {[...PROVIDERS, ...PROVIDERS].map((name, i) => (
            <LogoBlock key={`${name}-${i}`} name={name} glitch={glitchIndices.includes(i % PROVIDERS.length)} />
          ))}
        </div>
      </motion.div>
    </section>
  );
}

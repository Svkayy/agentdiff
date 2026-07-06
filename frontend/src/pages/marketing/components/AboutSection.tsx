import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { SectionLabel } from "@/components/system/SectionLabel";
import { ScrambleText } from "@/components/system/ScrambleText";

const ease = [0.22, 1, 0.36, 1] as const;

/** Clearly-decorative session tick (ornamental — not a real uptime metric). */
function SessionTick() {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const format = (n: number) => {
    const h = Math.floor(n / 3600);
    const m = Math.floor((n % 3600) / 60);
    const s = n % 60;
    return `${String(h).padStart(2, "0")}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
  };

  return (
    <span className="font-mono text-[#ea580c]" style={{ fontVariantNumeric: "tabular-nums" }}>
      {format(seconds)}
    </span>
  );
}

/**
 * A real before/after agent topology — AgentDiff's signature product visual.
 * The orchestrator routes to retriever / fact_checker / summarizer; a search
 * tool leaf hangs off retriever + fact_checker. In the CANDIDATE (after)
 * column the `fact_checker` sub-agent has STOPPED firing (solid #ea580c) — the
 * exact regression the terminal card attributes to `agents/router.py:42`.
 */
function TopologyColumn({ stopped }: { stopped: boolean }) {
  // Node layout in a 200×360 column.
  const NODES: { id: string; label: string; x: number; y: number; stop?: boolean }[] = [
    { id: "orchestrator", label: "orchestrator", x: 100, y: 44 },
    { id: "retriever", label: "retriever", x: 44, y: 150 },
    { id: "fact_checker", label: "fact_checker", x: 156, y: 150, stop: true },
    { id: "summarizer", label: "summarizer", x: 100, y: 256 },
    { id: "search", label: "search()", x: 100, y: 336 },
  ];
  const EDGES: [string, string][] = [
    ["orchestrator", "retriever"],
    ["orchestrator", "fact_checker"],
    ["retriever", "summarizer"],
    ["fact_checker", "summarizer"],
    ["retriever", "search"],
    ["fact_checker", "search"],
  ];
  const byId = (id: string) => NODES.find((n) => n.id === id)!;
  const nodeW = 82;
  const nodeH = 30;
  const cx = (n: { x: number }) => n.x;
  const cy = (n: { y: number }) => n.y;

  return (
    <g>
      {/* edges */}
      {EDGES.map(([f, t], i) => {
        const from = byId(f);
        const to = byId(t);
        // An edge into the stopped node reads as severed in the candidate.
        const severed = stopped && (t === "fact_checker" || f === "fact_checker");
        return (
          <line
            key={i}
            x1={cx(from)}
            y1={cy(from)}
            x2={cx(to)}
            y2={cy(to)}
            stroke={severed ? "#ea580c" : "hsl(var(--background))"}
            strokeWidth={severed ? 1.5 : 1}
            strokeDasharray={severed ? "4 4" : undefined}
            opacity={severed ? 0.8 : 0.4}
          />
        );
      })}
      {/* nodes */}
      {NODES.map((n) => {
        const isStopped = stopped && n.stop;
        const isTool = n.id === "search";
        return (
          <g key={n.id}>
            <rect
              x={n.x - nodeW / 2}
              y={n.y - nodeH / 2}
              width={nodeW}
              height={nodeH}
              rx={0}
              fill={isStopped ? "#ea580c" : "hsl(var(--foreground))"}
              stroke={isStopped ? "#ea580c" : "hsl(var(--background))"}
              strokeWidth={1.5}
              strokeDasharray={isTool ? "3 3" : undefined}
            />
            <text
              x={n.x}
              y={n.y + 4}
              textAnchor="middle"
              fill="hsl(var(--background))"
              fontSize={10}
              fontFamily="var(--font-mono), monospace"
              fontWeight={600}
              letterSpacing="0.02em"
            >
              {n.label}
            </text>
            {isStopped && (
              <circle cx={n.x} cy={n.y} r={nodeW / 2 + 6} fill="none" stroke="#ea580c" strokeWidth={1}>
                <animate attributeName="opacity" values="0.6;0.15;0.6" dur="3s" repeatCount="indefinite" />
              </circle>
            )}
          </g>
        );
      })}
    </g>
  );
}

function AgentTopology() {
  return (
    <svg
      viewBox="0 0 440 400"
      className="w-full h-full"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Before/after agent topology: in the candidate run the fact_checker sub-agent has stopped firing"
    >
      {/* column captions */}
      <text
        x={110}
        y={26}
        textAnchor="middle"
        fill="hsl(var(--background))"
        fontSize={11}
        fontFamily="var(--font-mono), monospace"
        letterSpacing="0.18em"
        opacity={0.7}
      >
        BASELINE
      </text>
      <text
        x={330}
        y={26}
        textAnchor="middle"
        fill="#ea580c"
        fontSize={11}
        fontFamily="var(--font-mono), monospace"
        letterSpacing="0.18em"
      >
        CANDIDATE
      </text>
      {/* divider */}
      <line x1={220} y1={40} x2={220} y2={392} stroke="hsl(var(--background))" strokeWidth={1} opacity={0.25} />
      <g transform="translate(10, 40)">
        <TopologyColumn stopped={false} />
      </g>
      <g transform="translate(230, 40)">
        <TopologyColumn stopped />
      </g>
    </svg>
  );
}

// Truthful figures: 8 provider parsers, 4 framework adapters, 5 behavioral
// delta families (agent-invocation rate, tool usage, latency, tokens, error
// rate), and the LLM judge which is strictly optional.
const STATS = [
  { label: "PROVIDERS", value: "8" },
  { label: "FRAMEWORKS", value: "4" },
  { label: "DELTA_METRICS", value: "5" },
  { label: "LLM_JUDGE", value: "OPTIONAL" },
];

function StatBlock({ label, value, index }: { label: string; value: string; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, filter: "blur(4px)" }}
      whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      viewport={{ once: true, margin: "-30px" }}
      transition={{ delay: 0.15 + index * 0.08, duration: 0.5, ease }}
      className="flex flex-col gap-1 border-2 border-foreground px-4 py-3"
    >
      <span className="text-[11px] tracking-[0.16em] uppercase text-muted-foreground font-mono">{label}</span>
      <span className="text-xl lg:text-2xl font-mono font-bold tracking-tight">
        <ScrambleText text={value} />
      </span>
    </motion.div>
  );
}

/**
 * About / methodology section — ported from the template's `about-section.tsx`.
 * Left: an abstract AGENT_GRAPH.svg composition (drawn, honestly labeled).
 * Right: METHODOLOGY-flavored copy — deterministic capture → compare →
 * attribute, the LLM never decides verdicts — plus a truthful stats grid.
 */
export function AboutSection() {
  return (
    <section className="w-full px-6 py-20 lg:px-12">
      <SectionLabel label="METHODOLOGY" index={2} />

      <div className="flex flex-col lg:flex-row gap-0 border-2 border-foreground">
        {/* Left: abstract composition */}
        <motion.div
          initial={{ opacity: 0, x: -30, filter: "blur(6px)" }}
          whileInView={{ opacity: 1, x: 0, filter: "blur(0px)" }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.7, ease }}
          className="relative w-full lg:w-1/2 min-h-[300px] lg:min-h-[500px] border-b-2 lg:border-b-0 lg:border-r-2 border-foreground overflow-hidden bg-foreground"
        >
          <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-4 py-3">
            <span className="text-[11px] tracking-[0.16em] uppercase text-background/70 font-mono">
              {"AGENT_GRAPH: baseline → candidate"}
            </span>
            <span className="text-[11px] tracking-[0.16em] uppercase text-[#ea580c] font-mono font-bold">
              FAIL
            </span>
          </div>

          <div className="absolute inset-0 flex items-center justify-center px-5 pt-12 pb-12">
            <AgentTopology />
          </div>

          <div className="absolute bottom-0 left-0 right-0 z-10 flex items-center justify-between px-4 py-3">
            <span className="text-[11px] tracking-[0.16em] uppercase text-background/60 font-mono">
              {"fact_checker: STOPPED"}
            </span>
            <span className="text-[11px] tracking-[0.16em] uppercase text-background/60 font-mono">
              {"1 SUB-AGENT REGRESSED"}
            </span>
          </div>
        </motion.div>

        {/* Right: content */}
        <motion.div
          initial={{ opacity: 0, x: 30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.7, delay: 0.1, ease }}
          className="flex flex-col w-full lg:w-1/2"
        >
          <div className="flex items-center justify-between px-5 py-3 border-b-2 border-foreground">
            <span className="text-[11px] tracking-[0.16em] uppercase text-muted-foreground font-mono">
              METHODOLOGY.md
            </span>
            <span className="text-[11px] tracking-[0.16em] uppercase text-muted-foreground font-mono">
              deterministic
            </span>
          </div>

          <div className="flex-1 flex flex-col justify-between px-5 py-6 lg:py-8">
            <div className="flex flex-col gap-6">
              <motion.h2
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-30px" }}
                transition={{ duration: 0.5, delay: 0.2, ease }}
                className="text-2xl lg:text-3xl font-mono font-bold tracking-tight uppercase text-balance"
              >
                Capture. Compare.
                <br />
                <span className="text-[#ea580c]">Attribute.</span>
              </motion.h2>

              <motion.div
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-30px" }}
                transition={{ delay: 0.3, duration: 0.5, ease }}
                className="flex flex-col gap-4"
              >
                <p className="text-sm lg:text-base font-mono text-foreground/75 leading-relaxed">
                  AgentDiff records your agent&apos;s trajectories through transport
                  and SDK shims, samples baseline against candidate, and computes
                  behavioral deltas with two-proportion tests and
                  Benjamini-Hochberg correction at a = 0.05. The verdict is
                  deterministic — the same runs always produce the same result.
                </p>
                <p className="text-sm lg:text-base font-mono text-foreground/75 leading-relaxed">
                  When a delta is significant, attribution walks the diff to name
                  the hunk that caused it. An LLM judge is available for
                  qualitative signals, but the LLM never decides the pass/warn/fail
                  verdict — statistics do.
                </p>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, scaleX: 0.8 }}
                whileInView={{ opacity: 1, scaleX: 1 }}
                viewport={{ once: true }}
                transition={{ delay: 0.4, duration: 0.5, ease }}
                style={{ transformOrigin: "left" }}
                className="flex items-center gap-3 py-3 border-t-2 border-b-2 border-foreground"
              >
                <span className="h-1.5 w-1.5 bg-[#ea580c] animate-blink" />
                <span className="text-[11px] tracking-[0.16em] uppercase text-muted-foreground font-mono">
                  SESSION:
                </span>
                <SessionTick />
              </motion.div>
            </div>

            <div className="grid grid-cols-2 gap-0 mt-6">
              {STATS.map((stat, i) => (
                <StatBlock key={stat.label} {...stat} index={i} />
              ))}
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

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
 *
 * Interactive: hovering (or tapping, which pins) a node highlights it in BOTH
 * columns, dims unrelated edges, and swaps the bottom nameplate readout to
 * that node's baseline → candidate invocation rate. Rates match the terminal
 * card in RAW_DATA (fact_checker 0.98 → 0.10).
 */
type TopologyNode = {
  id: string;
  label: string;
  x: number;
  y: number;
  base: number;
  cand: number;
  status: "OK" | "STOPPED" | "DEGRADED";
  stop?: boolean;
};

// Node layout in a 200×360 column.
const NODES: TopologyNode[] = [
  { id: "orchestrator", label: "orchestrator", x: 100, y: 44, base: 1.0, cand: 1.0, status: "OK" },
  { id: "retriever", label: "retriever", x: 50, y: 150, base: 0.98, cand: 0.98, status: "OK" },
  { id: "fact_checker", label: "fact_checker", x: 150, y: 150, base: 0.98, cand: 0.1, status: "STOPPED", stop: true },
  { id: "summarizer", label: "summarizer", x: 100, y: 256, base: 1.0, cand: 1.0, status: "OK" },
  { id: "search", label: "search()", x: 100, y: 336, base: 0.86, cand: 0.44, status: "DEGRADED" },
];
const EDGES: [string, string][] = [
  ["orchestrator", "retriever"],
  ["orchestrator", "fact_checker"],
  ["retriever", "summarizer"],
  ["fact_checker", "summarizer"],
  ["retriever", "search"],
  ["fact_checker", "search"],
];
const nodeById = (id: string) => NODES.find((n) => n.id === id)!;

function TopologyColumn({
  stopped,
  active,
  onHover,
  onPin,
}: {
  stopped: boolean;
  active: string | null;
  onHover: (id: string | null) => void;
  onPin: (id: string) => void;
}) {
  const nodeW = 88;
  const nodeH = 30;

  return (
    <g>
      {/* edges */}
      {EDGES.map(([f, t], i) => {
        const from = nodeById(f);
        const to = nodeById(t);
        // An edge into the stopped node reads as severed in the candidate.
        const severed = stopped && (t === "fact_checker" || f === "fact_checker");
        const touched = active !== null && (f === active || t === active);
        const dimmed = active !== null && !touched;
        return (
          <line
            key={i}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            stroke={severed ? "#ea580c" : "hsl(var(--background))"}
            strokeWidth={severed || touched ? 1.5 : 1}
            strokeDasharray={severed ? "4 4" : undefined}
            opacity={dimmed ? 0.12 : touched ? 0.9 : severed ? 0.8 : 0.4}
            style={{ transition: "opacity 150ms ease-out" }}
          />
        );
      })}
      {/* nodes */}
      {NODES.map((n) => {
        const isStopped = stopped && n.stop;
        const isTool = n.id === "search";
        const isActive = active === n.id;
        const dimmed = active !== null && !isActive;
        return (
          <g
            key={n.id}
            onMouseEnter={() => onHover(n.id)}
            onMouseLeave={() => onHover(null)}
            onClick={() => onPin(n.id)}
            style={{ cursor: "crosshair", transition: "opacity 150ms ease-out" }}
            opacity={dimmed ? 0.35 : 1}
          >
            <rect
              x={n.x - nodeW / 2}
              y={n.y - nodeH / 2}
              width={nodeW}
              height={nodeH}
              rx={0}
              fill={isStopped ? "#ea580c" : "hsl(var(--foreground))"}
              stroke={isActive ? "#ea580c" : isStopped ? "#ea580c" : "hsl(var(--background))"}
              strokeWidth={isActive ? 2 : 1.5}
              strokeDasharray={isTool ? "3 3" : undefined}
            />
            <text
              x={n.x}
              y={n.y + 4}
              textAnchor="middle"
              fill="hsl(var(--background))"
              fontSize={11}
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

function AgentTopology({
  active,
  onHover,
  onPin,
}: {
  active: string | null;
  onHover: (id: string | null) => void;
  onPin: (id: string) => void;
}) {
  return (
    <svg
      viewBox="0 0 440 400"
      className="w-full h-full"
      preserveAspectRatio="xMidYMid meet"
      aria-label="Before/after agent topology: in the candidate run the fact_checker sub-agent has stopped firing. Hover a node to read its baseline and candidate invocation rates."
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
        <TopologyColumn stopped={false} active={active} onHover={onHover} onPin={onPin} />
      </g>
      <g transform="translate(230, 40)">
        <TopologyColumn stopped active={active} onHover={onHover} onPin={onPin} />
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
 * Left: a real before/after AGENT_GRAPH.svg topology.
 * Right: METHODOLOGY-flavored copy — deterministic capture → compare →
 * attribute, the LLM never decides verdicts — plus a truthful stats grid.
 */
export function AboutSection() {
  // Hover previews a node; click/tap pins it (tap again to unpin) so touch
  // devices get the same readout. Hover wins while present.
  const [hovered, setHovered] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const active = hovered ?? pinned;
  const activeNode = active ? nodeById(active) : null;

  return (
    <section className="w-full px-6 py-20 lg:px-12">
      <SectionLabel label="METHODOLOGY" index={2} />

      <div className="flex flex-col lg:flex-row gap-0 border-2 border-foreground">
        {/* Left: before/after agent topology */}
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
            <AgentTopology
              active={active}
              onHover={setHovered}
              onPin={(id) => setPinned((p) => (p === id ? null : id))}
            />
          </div>

          <div className="absolute bottom-0 left-0 right-0 z-10 flex items-center justify-between px-4 py-3">
            {activeNode ? (
              <span
                className={`text-[11px] tracking-[0.16em] uppercase font-mono tabular ${
                  activeNode.status === "OK" ? "text-background/60" : "text-[#ea580c]"
                }`}
              >
                {`${activeNode.label}: ${activeNode.base.toFixed(2)} → ${activeNode.cand.toFixed(2)} [${activeNode.status}]`}
              </span>
            ) : (
              <span className="text-[11px] tracking-[0.16em] uppercase text-background/60 font-mono">
                {"fact_checker: STOPPED"}
              </span>
            )}
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

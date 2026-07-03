import { motion } from "framer-motion";
import { useSkipEntrance } from "@/lib/utils";

// DESIGN.md palette — ember is reserved for the regression signal only.
const EMBER = "#FF4D2E";
const PASS = "#3FB27F";
const NODE_FILL = "#1B2027";
const NODE_BORDER = "#2A313B";
const TEXT = "#E8EBEF";
const MUTED = "#8A929C";
const EDGE = "#2A313B";

interface NodeSpec {
  id: string;
  x: number;
  y: number;
  label: string;
  rate: string;
  stopped?: boolean;
}

const W = 300;
const H = 236;
const NODE_W = 108;
const NODE_H = 40;

const NODES: NodeSpec[] = [
  { id: "orchestrator", x: 96, y: 18, label: "orchestrator", rate: "100%" },
  { id: "retriever", x: 12, y: 108, label: "retriever", rate: "100%" },
  { id: "fact_checker", x: 96, y: 178, label: "fact_checker", rate: "100%" },
  { id: "summarizer", x: 180, y: 108, label: "summarizer", rate: "100%" },
];

const CANDIDATE_RATES: Record<string, string> = {
  orchestrator: "100%",
  retriever: "100%",
  fact_checker: "0%",
  summarizer: "100%",
};

function edgePath(a: NodeSpec, b: NodeSpec): string {
  const ax = a.x + NODE_W / 2;
  const ay = a.y + NODE_H;
  const bx = b.x + NODE_W / 2;
  const by = b.y;
  const my = (ay + by) / 2;
  return `M ${ax} ${ay} C ${ax} ${my}, ${bx} ${my}, ${bx} ${by}`;
}

function GraphPanel({
  title,
  verdict,
  candidate,
  skip,
}: {
  title: string;
  verdict: "PASS" | "FAIL";
  candidate: boolean;
  skip: boolean;
}) {
  const orchestrator = NODES[0];
  const enter = (i: number) => ({
    initial: skip ? false : { opacity: 0, scale: 0.96 },
    animate: { opacity: 1, scale: 1 },
    transition: { duration: 0.32, ease: "easeOut" as const, delay: 0.15 + i * 0.08 },
  });

  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-baseline justify-between px-1 pb-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em]" style={{ color: MUTED }}>
          {title}
        </span>
        <span
          className="font-mono text-[11px] font-medium tabular"
          style={{ color: verdict === "FAIL" ? EMBER : PASS }}
        >
          {verdict}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`${title} agent graph, verdict ${verdict}`}
        className="w-full"
      >
        {NODES.slice(1).map((n, i) => {
          const stoppedEdge = candidate && n.id === "fact_checker";
          return orchestrator ? (
            <motion.path
              key={`e-${n.id}`}
              d={edgePath(orchestrator, n)}
              fill="none"
              stroke={stoppedEdge ? EMBER : EDGE}
              strokeWidth={1.25}
              strokeDasharray={stoppedEdge ? "3 4" : undefined}
              strokeOpacity={stoppedEdge ? 0.7 : 1}
              initial={skip ? false : { pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.32, ease: "easeOut", delay: 0.3 + i * 0.08 }}
            />
          ) : null;
        })}

        {NODES.map((n, i) => {
          const stopped = candidate && n.id === "fact_checker";
          const rate = candidate ? CANDIDATE_RATES[n.id] ?? n.rate : n.rate;
          return (
            <motion.g key={n.id} {...enter(i)}>
              {stopped && (
                // The ONE ember pulse: a single halo expand-and-settle on load.
                <motion.rect
                  x={n.x}
                  y={n.y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={10}
                  fill="none"
                  stroke={EMBER}
                  initial={skip ? false : { opacity: 0.9, scale: 1, strokeWidth: 1.5 }}
                  animate={{ opacity: 0, scale: 1.28, strokeWidth: 0.5 }}
                  transition={{ duration: 0.6, ease: "easeOut", delay: 0.9 }}
                  style={{ transformOrigin: `${n.x + NODE_W / 2}px ${n.y + NODE_H / 2}px` }}
                />
              )}
              <rect
                x={n.x}
                y={n.y}
                width={NODE_W}
                height={NODE_H}
                rx={10}
                fill={NODE_FILL}
                stroke={stopped ? EMBER : NODE_BORDER}
                strokeWidth={stopped ? 1.5 : 1}
              />
              <circle
                cx={n.x + 14}
                cy={n.y + NODE_H / 2}
                r={3}
                fill={stopped ? EMBER : PASS}
              />
              <text
                x={n.x + 26}
                y={n.y + 17}
                fontSize={10}
                fontFamily="'JetBrains Mono', monospace"
                fill={TEXT}
              >
                {n.label}
              </text>
              <text
                x={n.x + 26}
                y={n.y + 31}
                fontSize={9}
                fontFamily="'JetBrains Mono', monospace"
                fill={stopped ? EMBER : MUTED}
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {stopped ? `${rate} · stopped` : `fired ${rate}`}
              </text>
            </motion.g>
          );
        })}
      </svg>
    </div>
  );
}

/**
 * The hero visual: a framed dark plate showing the before/after agent graph.
 * Baseline (origin/main) on the left, candidate (working tree) on the right,
 * where fact_checker has silently stopped firing — the one ember signal.
 */
export function GraphPlate() {
  const skip = useSkipEntrance();
  return (
    <motion.figure
      initial={skip ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: "easeOut", delay: 0.1 }}
      className="overflow-hidden rounded-lg border border-hairline bg-canvas shadow-[0_24px_60px_rgba(21,24,29,0.18)]"
    >
      <div className="flex items-center justify-between border-b border-nodeborder px-5 py-3">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-canvastext">
          agentdiff compare · origin/main → working
        </span>
        <span className="font-mono text-[11px] tabular" style={{ color: MUTED }}>
          n=20 · hermetic
        </span>
      </div>
      <div className="dot-grid-dark flex flex-col gap-6 p-5 sm:flex-row sm:gap-4">
        <GraphPanel title="baseline · origin/main" verdict="PASS" candidate={false} skip={skip} />
        <div aria-hidden="true" className="hidden w-px self-stretch bg-nodeborder sm:block" />
        <GraphPanel title="candidate · working" verdict="FAIL" candidate skip={skip} />
      </div>
      <figcaption className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-nodeborder px-5 py-3 font-mono text-[11px]">
        <span style={{ color: EMBER }}>fact_checker: 100% → 0%</span>
        <span style={{ color: MUTED }}>p&lt;0.001 · two-proportion</span>
        <span style={{ color: MUTED }}>cause: agents/fact_checker.py · call_removed</span>
      </figcaption>
    </motion.figure>
  );
}

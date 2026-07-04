import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import { motion } from "framer-motion";
import { fetchRun, type RunDetail, type Finding } from "@/lib/api";
import { useSkipEntrance } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { GraphNode, StatisticalEvidence } from "@/types";
import { verdictLabel } from "./ProjectPage";

// ── Design tokens (light plate — user-approved) ───────────────────────────────
const EMBER = "#FF4D2E";
const PASS = "#3FB27F";
const NODE_FILL = "#FFFFFF";
const NODE_BORDER = "#E6E3DD";
const TEXT = "#15181D";
const MUTED = "#8A929C";
const EDGE = "#E6E3DD";

// ── Verdict / kind badges ─────────────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: string | null }) {
  const styles: Record<string, string> = {
    pass: "bg-verdict-pass/10 text-verdict-pass border border-verdict-pass/30",
    warn: "bg-verdict-warn/10 text-verdict-warn border border-verdict-warn/30",
    fail: "bg-ember/10 text-ember border border-ember/30",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest",
        verdict ? styles[verdict] ?? "border border-hairline text-neutral-faint" : "text-neutral-faint",
      )}
      title={verdict ?? undefined}
    >
      {verdictLabel(verdict)}
    </span>
  );
}

function KindBadge({ kind }: { kind: string }) {
  return kind === "drift" ? (
    <span className="inline-flex items-center rounded-sm border border-ember/30 px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest text-ember">
      Live Drift
    </span>
  ) : (
    <span className="inline-flex items-center rounded-sm border border-hairline px-sm py-2xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
      CI
    </span>
  );
}

// ── Real processed graph ─────────────────────────────────────────────────────

const NODE_W = 154;
const NODE_H = 48;
const GRAPH_W = 620;
const COL_AGENT_X = 64;
const COL_TOOL_X = 402;
const ROW_DY = 82;

type PositionedNode = GraphNode & { x: number; y: number };

function formatNodeRate(node: GraphNode): string {
  if (node.kind === "agent") {
    return `${Math.round(node.baseline_rate * 100)}% → ${Math.round(node.candidate_rate * 100)}%`;
  }
  return `${node.baseline_rate.toFixed(1)} → ${node.candidate_rate.toFixed(1)}`;
}

function layoutGraph(nodes: GraphNode[]): PositionedNode[] {
  const agents = nodes.filter((n) => n.kind === "agent");
  const tools = nodes.filter((n) => n.kind !== "agent");
  const place = (list: GraphNode[], x: number) =>
    list.map((node, i) => ({ ...node, x, y: 28 + i * ROW_DY }));
  return [...place(agents, COL_AGENT_X), ...place(tools, tools.length ? COL_TOOL_X : COL_AGENT_X)];
}

function edgePath(source: PositionedNode, target: PositionedNode): string {
  const sx = source.x + NODE_W;
  const sy = source.y + NODE_H / 2;
  const tx = target.x;
  const ty = target.y + NODE_H / 2;
  const mid = (sx + tx) / 2;
  return `M ${sx} ${sy} C ${mid} ${sy}, ${mid} ${ty}, ${tx} ${ty}`;
}

function GraphNodeRect({ node, index, skip }: { node: PositionedNode; index: number; skip: boolean }) {
  const stopped = node.stopped;
  const verdictColor =
    stopped || node.verdict === "fail" ? EMBER : node.verdict === "warn" ? "#E8A33D" : PASS;
  const label = node.label.length > 18 ? `${node.label.slice(0, 18)}…` : node.label;

  return (
    <motion.g
      initial={skip ? false : { opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.28, ease: "easeOut", delay: 0.12 + index * 0.04 }}
    >
      <rect
        x={node.x}
        y={node.y}
        width={NODE_W}
        height={NODE_H}
        rx={6}
        fill={NODE_FILL}
        stroke={stopped ? EMBER : NODE_BORDER}
        strokeWidth={stopped ? 1.5 : 1}
      />
      <circle cx={node.x + 15} cy={node.y + 17} r={3.5} fill={verdictColor} />
      <text
        x={node.x + 27}
        y={node.y + 18}
        fontSize={10}
        fontFamily="'JetBrains Mono', monospace"
        fill={stopped ? EMBER : TEXT}
        fontWeight={stopped ? 700 : 500}
      >
        {label}
      </text>
      <text
        x={node.x + 14}
        y={node.y + 35}
        fontSize={9}
        fontFamily="'JetBrains Mono', monospace"
        fill={MUTED}
      >
        {formatNodeRate(node)}
      </text>
    </motion.g>
  );
}

function AgentGraph({ run }: { run: RunDetail }) {
  const skip = useSkipEntrance();
  const nodes = layoutGraph(run.graph.nodes);
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const graphH = Math.max(
    170,
    (nodes.length ? Math.max(...nodes.map((node) => node.y)) : 0) + NODE_H + 28,
  );
  const stoppedCount = run.graph.nodes.filter((n) => n.stopped).length;

  return (
    <motion.figure
      initial={skip ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: "easeOut", delay: 0.1 }}
      className="mb-2xl overflow-hidden rounded-lg border border-hairline bg-white shadow-[0_4px_24px_rgba(21,24,29,0.06)]"
    >
      <div className="flex items-center justify-between border-b border-hairline px-5 py-3">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-neutral-faint">
          agentdiff compare · {run.baseline_ref?.slice(0, 7)} → {run.candidate_ref?.slice(0, 7)}
        </span>
        <span className="font-mono text-[11px] tabular-nums" style={{ color: MUTED }}>
          {run.graph.nodes.length} nodes · {run.graph.edges.length} edges
        </span>
      </div>
      <div className="dot-grid-light overflow-x-auto p-5">
        {nodes.length === 0 ? (
          <div className="py-xl text-center text-small text-neutral-muted">
            No processed graph data for this run.
          </div>
        ) : (
          <svg
            viewBox={`0 0 ${GRAPH_W} ${graphH}`}
            role="img"
            aria-label="Processed AgentDiff graph"
            className="min-w-[620px] w-full"
          >
            {run.graph.edges.map((edge, index) => {
              const source = byId.get(edge.source);
              const target = byId.get(edge.target);
              if (!source || !target) return null;
              const broken = source.stopped || target.stopped;
              return (
                <motion.path
                  key={`${edge.source}-${edge.target}`}
                  d={edgePath(source, target)}
                  fill="none"
                  stroke={broken ? EMBER : EDGE}
                  strokeWidth={1.4}
                  strokeDasharray={broken ? "4 5" : undefined}
                  initial={skip ? false : { pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                  transition={{ duration: 0.32, ease: "easeOut", delay: 0.18 + index * 0.04 }}
                />
              );
            })}
            {nodes.map((node, index) => (
              <GraphNodeRect key={node.id} node={node} index={index} skip={skip} />
            ))}
          </svg>
        )}
      </div>
      {stoppedCount > 0 && (
        <figcaption className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-hairline px-5 py-3 font-mono text-[11px]">
          {run.graph.nodes.filter((n) => n.stopped).map((node) => (
            <span key={node.id} style={{ color: EMBER }}>{node.label}: stopped</span>
          ))}
        </figcaption>
      )}
    </motion.figure>
  );
}

// ── Findings list ─────────────────────────────────────────────────────────────

function fmtP(evidence: StatisticalEvidence): string {
  const p = evidence.p_value;
  if (p === null) return "p=—";
  const raw = p < 0.001 ? "p<0.001" : `p=${p.toFixed(3)}`;
  return evidence.significant ? `${raw}*` : raw;
}

function fmtEffect(evidence: StatisticalEvidence): string | null {
  if (evidence.effect_size === null) return null;
  const label =
    evidence.effect_label === "cohens_h"
      ? "h"
      : evidence.effect_label === "cliffs_delta"
        ? "Cliff"
        : evidence.effect_label;
  return `${label}=${evidence.effect_size.toFixed(2)}`;
}

function fmtCi(evidence: StatisticalEvidence): string | null {
  if (!evidence.confidence_interval) return null;
  const [lo, hi] = evidence.confidence_interval;
  return `95% CI ${Math.round(lo * 100)}% to ${Math.round(hi * 100)}%`;
}

function StatisticalEvidenceBar({ evidence }: { evidence: StatisticalEvidence | null }) {
  if (!evidence) return null;
  const effect = fmtEffect(evidence);
  const ci = fmtCi(evidence);
  return (
    <div className="mt-sm flex flex-wrap items-center gap-xs font-mono text-micro text-neutral-faint">
      <span className="rounded-sm border border-hairline px-sm py-2xs">{evidence.test}</span>
      <span className={evidence.significant ? "text-ink-dark" : undefined}>{fmtP(evidence)}</span>
      {effect && <span>{effect}</span>}
      {ci && <span>{ci}</span>}
      <span>
        n={evidence.baseline_n}/{evidence.candidate_n}
      </span>
    </div>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  return (
    <div className="rounded-md border border-hairline bg-white p-lg">
      <div className="mb-sm flex flex-wrap items-center gap-sm">
        <span
          className={cn(
            "rounded-sm px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest",
            finding.verdict === "fail"
              ? "bg-ember/10 text-ember"
              : finding.verdict === "warn"
              ? "bg-verdict-warn/10 text-verdict-warn"
              : "bg-verdict-pass/10 text-verdict-pass",
          )}
          title={finding.verdict}
        >
          {verdictLabel(finding.verdict)}
        </span>
        {finding.cause_rule && (
          <span className="rounded-sm border border-hairline px-sm py-2xs font-mono text-micro text-neutral-faint">
            {finding.cause_rule}
          </span>
        )}
        <span className="font-mono text-micro text-neutral-faint">{finding.metric}</span>
      </div>
      <h3 className="mb-xs font-display text-small font-bold text-ink-dark">{finding.title}</h3>
      <p className="mb-sm text-small text-neutral-muted">{finding.impact_summary}</p>
      <StatisticalEvidenceBar evidence={finding.statistical_evidence} />
      {finding.cause_path && (
        <div className="mt-sm font-mono text-micro text-neutral-faint">{finding.cause_path}</div>
      )}
      {finding.cause_hunk && (
        <div className="mt-sm overflow-x-auto rounded-sm border border-hairline bg-[#FAFAF8] px-md py-sm">
          <pre className="font-mono text-micro text-ink-dark whitespace-pre">
            {finding.cause_hunk}
          </pre>
        </div>
      )}
      {finding.explanation && (
        <p className="mt-sm text-small text-neutral-muted">{finding.explanation}</p>
      )}
    </div>
  );
}

// ── Drift callout ─────────────────────────────────────────────────────────────

function DriftCallout() {
  return (
    <div className="mb-xl rounded-md border border-ember/30 bg-ember/5 p-lg">
      <div className="mb-xs font-mono text-micro font-bold uppercase tracking-widest text-ember">
        Model drift detected
      </div>
      <p className="text-small text-ink-dark">
        Suspected upstream model drift — no attributable code change found in the
        candidate ref. Behavioral delta may be caused by a model update or sampling
        shift.
      </p>
    </div>
  );
}

// ── RunDetailPage ─────────────────────────────────────────────────────────────

export function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const runId = id ?? "";
  const { getToken } = useAuth();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetchRun(runId, getToken)
      .then((data) => {
        setRun(data);
        setError(null);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Failed to load run");
      })
      .finally(() => setLoading(false));
  }, [runId, getToken]);

  return (
    <div className="mx-auto w-full max-w-[1240px] px-xl py-2xl">
      {/* Breadcrumb */}
      <div className="mb-xl flex items-center gap-xs font-mono text-micro text-neutral-faint">
        <Link to="/" className="transition-colors hover:text-ink-dark">
          Projects
        </Link>
        <span>/</span>
        {run && (
          <>
            <span className="text-ink-dark">Run</span>
            <span>/</span>
          </>
        )}
        <span className="text-ink-dark">{runId.slice(0, 8)}…</span>
      </div>

      {loading && (
        <div className="space-y-md">
          <div className="h-10 w-64 animate-pulse rounded-sm border border-hairline bg-hairline" />
          <div className="h-64 animate-pulse rounded-md border border-hairline bg-hairline" />
        </div>
      )}

      {error && (
        <div className="rounded-sm border border-ember/30 bg-ember/5 px-md py-sm text-small text-ember">
          {error}
        </div>
      )}

      {run && (
        <>
          {/* Header */}
          <div className="mb-2xl">
            <div className="mb-sm flex flex-wrap items-center gap-sm">
              <VerdictBadge verdict={run.verdict} />
              <KindBadge kind={run.kind} />
              <span className="font-mono text-micro text-neutral-faint">
                {new Date(run.created_at).toLocaleString()}
              </span>
            </div>
            <h1 className="font-display text-h1 font-bold text-ink-dark">
              Run detail
            </h1>
            <div className="mt-xs font-mono text-micro text-neutral-faint">
              <span className="text-ink-dark">{run.baseline_ref}</span>
              <span className="mx-xs">→</span>
              <span className="text-ink-dark">{run.candidate_ref}</span>
              <span className="mx-sm text-neutral-faint">·</span>
              <span>
                n={run.baseline_samples} vs {run.candidate_samples} samples
              </span>
            </div>
          </div>

          {/* Drift callout for drift runs with no cause_path */}
          {run.kind === "drift" &&
            run.findings.every((f) => !f.cause_path) &&
            run.findings.length > 0 && <DriftCallout />}

          {/* Agent graph hero */}
          <AgentGraph run={run} />

          {/* Findings */}
          <div>
            <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
              Findings
            </div>
            <h2 className="mb-lg font-display text-h2 font-bold text-ink-dark">
              {run.findings.length} finding{run.findings.length !== 1 ? "s" : ""}
            </h2>

            {run.findings.length === 0 ? (
              <div className="rounded-md border border-hairline bg-white py-xl text-center text-small text-neutral-muted">
                No findings — all behavioral metrics within thresholds.
              </div>
            ) : (
              <div className="space-y-md">
                {run.findings.map((f) => (
                  <FindingRow key={f.test_case_id + f.title} finding={f} />
                ))}
              </div>
            )}
          </div>

          {/* Error from run engine */}
          {run.error && (
            <div className="mt-2xl rounded-sm border border-ember/30 bg-ember/5 px-md py-sm">
              <div className="mb-xs font-mono text-micro uppercase tracking-widest text-ember">
                Run error
              </div>
              <pre className="whitespace-pre-wrap font-mono text-micro text-ember">
                {run.error}
              </pre>
            </div>
          )}
        </>
      )}
    </div>
  );
}

import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import { motion } from "framer-motion";
import { fetchRun, type RunDetail, type Finding } from "@/lib/api";
import { useSkipEntrance } from "@/lib/utils";
import { cn } from "@/lib/utils";

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
  const v = verdict ?? "—";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest",
        verdict ? styles[verdict] ?? "border border-hairline text-neutral-faint" : "text-neutral-faint",
      )}
    >
      {v}
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

// ── Light agent graph ─────────────────────────────────────────────────────────

interface AgentSpec {
  name: string;
  function?: string;
}

const NODE_W = 120;
const NODE_H = 44;
const PLATE_W = 320;

function layoutNodes(agents: AgentSpec[]): Array<AgentSpec & { x: number; y: number }> {
  // Simple vertical layout with orchestrator at top
  const spacing = 72;
  return agents.map((a, i) => ({
    ...a,
    x: (PLATE_W - NODE_W) / 2,
    y: 16 + i * spacing,
  }));
}

function edgePath(
  ay: number,
  by: number,
  cx: number,
): string {
  const ax = cx;
  const bx = cx;
  const mid = (ay + NODE_H + by) / 2;
  return `M ${ax} ${ay + NODE_H} C ${ax} ${mid}, ${bx} ${mid}, ${bx} ${by}`;
}

function GraphPanel({
  title,
  verdict,
  agents,
  stoppedAgents,
  side,
  skip,
}: {
  title: string;
  verdict: "PASS" | "FAIL" | null;
  agents: Array<AgentSpec & { x: number; y: number }>;
  stoppedAgents: Set<string>;
  side: "baseline" | "candidate";
  skip: boolean;
}) {
  const plateH = 16 + agents.length * 72 + 16;
  const centerX = PLATE_W / 2;

  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-baseline justify-between px-1 pb-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em]" style={{ color: MUTED }}>
          {title}
        </span>
        {verdict && (
          <span
            className="font-mono text-[11px] font-medium tabular-nums"
            style={{ color: verdict === "FAIL" ? EMBER : PASS }}
          >
            {verdict}
          </span>
        )}
      </div>
      <svg
        viewBox={`0 0 ${PLATE_W} ${plateH}`}
        role="img"
        aria-label={`${title} agent graph, verdict ${verdict ?? "pending"}`}
        className="w-full"
      >
        {/* Edges between consecutive nodes */}
        {agents.slice(1).map((n, i) => {
          const prev = agents[i];
          const stoppedEdge = side === "candidate" && stoppedAgents.has(n.name);
          return (
            <motion.path
              key={`e-${n.name}`}
              d={edgePath(prev.y, n.y, centerX)}
              fill="none"
              stroke={stoppedEdge ? EMBER : EDGE}
              strokeWidth={1.25}
              strokeDasharray={stoppedEdge ? "3 4" : undefined}
              strokeOpacity={stoppedEdge ? 0.7 : 1}
              initial={skip ? false : { pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.32, ease: "easeOut", delay: 0.3 + i * 0.08 }}
            />
          );
        })}

        {/* Nodes */}
        {agents.map((n, i) => {
          const stopped = side === "candidate" && stoppedAgents.has(n.name);
          return (
            <motion.g
              key={n.name}
              initial={skip ? false : { opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.32, ease: "easeOut", delay: 0.15 + i * 0.08 }}
            >
              {stopped && (
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
                  style={{
                    transformOrigin: `${n.x + NODE_W / 2}px ${n.y + NODE_H / 2}px`,
                  }}
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
                {n.name.length > 14 ? n.name.slice(0, 14) + "…" : n.name}
              </text>
              <text
                x={n.x + 26}
                y={n.y + 31}
                fontSize={9}
                fontFamily="'JetBrains Mono', monospace"
                fill={stopped ? EMBER : MUTED}
              >
                {stopped ? "stopped" : "active"}
              </text>
            </motion.g>
          );
        })}
      </svg>
    </div>
  );
}

function AgentGraph({
  run,
  findings,
}: {
  run: RunDetail;
  findings: Finding[];
}) {
  const skip = useSkipEntrance();

  // Extract agents from run.config.agents if present
  type AgentConfig = { name?: string; function?: string };
  const configAgents = (
    Array.isArray((run.config as Record<string, unknown>)?.agents)
      ? ((run.config as Record<string, unknown>).agents as AgentConfig[])
      : []
  );

  const agents: AgentSpec[] =
    configAgents.length > 0
      ? configAgents.map((a) => ({ name: a.name ?? "agent", function: a.function }))
      : [
          { name: "orchestrator" },
          { name: "retriever" },
          { name: "executor" },
        ];

  const laidOut = layoutNodes(agents);

  // Which agents are "stopped" = have a failing finding whose title starts with agent name
  const stoppedAgents = new Set<string>(
    findings
      .filter((f) => f.verdict === "fail")
      .flatMap((f) =>
        agents.map((a) => a.name).filter((name) => {
          const t = f.title.toLowerCase();
          const n = name.toLowerCase();
          return t.startsWith(n) && (t.length === n.length || t[n.length] === " ");
        }),
      ),
  );

  const overallVerdict =
    run.verdict === "pass" ? "PASS" : run.verdict === "fail" ? "FAIL" : null;

  const plateH = 16 + agents.length * 72 + 16;

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
          {findings.length} finding{findings.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="dot-grid-light flex flex-col gap-6 p-5 sm:flex-row sm:gap-4" style={{ minHeight: plateH + 40 }}>
        <GraphPanel
          title={`baseline · ${run.baseline_ref?.slice(0, 7) ?? "—"}`}
          verdict="PASS"
          agents={laidOut}
          stoppedAgents={new Set()}
          side="baseline"
          skip={skip}
        />
        <div aria-hidden="true" className="hidden w-px self-stretch bg-hairline sm:block" />
        <GraphPanel
          title={`candidate · ${run.candidate_ref?.slice(0, 7) ?? "—"}`}
          verdict={overallVerdict}
          agents={laidOut}
          stoppedAgents={stoppedAgents}
          side="candidate"
          skip={skip}
        />
      </div>
      {stoppedAgents.size > 0 && (
        <figcaption className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-hairline px-5 py-3 font-mono text-[11px]">
          {Array.from(stoppedAgents).map((name) => (
            <span key={name} style={{ color: EMBER }}>
              {name}: stopped
            </span>
          ))}
        </figcaption>
      )}
    </motion.figure>
  );
}

// ── Findings list ─────────────────────────────────────────────────────────────

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
        >
          {finding.verdict}
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
      {finding.cause_path && (
        <div className="mt-sm font-mono text-micro text-neutral-faint">{finding.cause_path}</div>
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
            </div>
          </div>

          {/* Drift callout for drift runs with no cause_path */}
          {run.kind === "drift" &&
            run.findings.every((f) => !f.cause_path) &&
            run.findings.length > 0 && <DriftCallout />}

          {/* Agent graph hero */}
          <AgentGraph run={run} findings={run.findings} />

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

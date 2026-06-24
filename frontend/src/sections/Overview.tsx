import { useMemo, useState } from "react";
import { AgentGraph } from "@/components/AgentGraph";
import { StatChips } from "@/components/overview/StatChips";
import { EvalContrast } from "@/components/overview/EvalContrast";
import { shortRef } from "@/lib/payload";
import type { GraphNode, ReportData, Verdict } from "@/types";

// ── Verdict banner ───────────────────────────────────────────────────────────
function VerdictBanner({ verdict, baseRef, candRef }: {
  verdict: Verdict;
  baseRef: string;
  candRef: string;
}) {
  const isEmber = verdict === "fail";
  const accentClass = isEmber
    ? "text-ember"
    : verdict === "warn"
      ? "text-verdict-warn"
      : "text-verdict-pass";
  const borderClass = isEmber
    ? "border-ember/20 bg-ember/5"
    : verdict === "warn"
      ? "border-verdict-warn/20 bg-verdict-warn/5"
      : "border-verdict-pass/20 bg-verdict-pass/5";

  const label =
    verdict === "fail"
      ? "Behavioral Regression Detected"
      : verdict === "warn"
        ? "Behavioral Change — Review Recommended"
        : "No Behavioral Regression";

  const sub =
    verdict === "fail"
      ? "At least one agent stopped firing or tool usage dropped significantly."
      : verdict === "warn"
        ? "Minor behavioral shifts detected between the two runs."
        : "Agent behavior is statistically consistent across both runs.";

  return (
    <div className={`rounded-lg border px-xl py-lg ${borderClass}`}>
      <div className="flex items-start justify-between gap-lg">
        <div>
          <h1 className={`font-display text-display font-bold leading-tight ${accentClass}`}>
            {label}
          </h1>
          <p className="mt-xs text-body text-neutral-faint">{sub}</p>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-mono text-micro text-neutral-faint">Compare</div>
          <div className="mt-2xs font-mono text-small text-ink-light">
            <span>{baseRef}</span>
            <span className="mx-xs text-neutral-faint">→</span>
            <span>{candRef}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Graph plate ──────────────────────────────────────────────────────────────
function GraphPlate({
  data,
  selectedId,
  onSelect,
}: {
  data: ReportData;
  selectedId: string | null;
  onSelect: (n: GraphNode) => void;
}) {
  return (
    <div
      className="relative overflow-hidden rounded-lg border border-node-border"
      style={{ background: "#0E1116", height: "480px" }}
    >
      {/* Plate label */}
      <div className="absolute left-lg top-lg z-10 flex items-center gap-sm">
        <span className="font-display text-small font-semibold text-ink-light">
          Agent Graph
        </span>
        <span className="rounded-sm border border-node-border bg-node-fill px-xs py-2xs font-mono text-micro text-neutral-faint">
          before / after
        </span>
      </div>

      {/* React Flow fills the plate */}
      <AgentGraph
        graph={data.graph}
        selectedId={selectedId}
        onSelect={onSelect}
      />
    </div>
  );
}

// ── Selected node detail panel ────────────────────────────────────────────────
function NodeDetail({ node }: { node: GraphNode }) {
  const rateLabel = node.kind === "agent" ? "Firing Rate" : "Avg Calls / Run";
  const baseVal =
    node.kind === "agent"
      ? `${Math.round(node.baseline_rate * 100)}%`
      : node.baseline_rate.toFixed(1);
  const candVal =
    node.kind === "agent"
      ? `${Math.round(node.candidate_rate * 100)}%`
      : node.candidate_rate.toFixed(1);

  const isEmber = node.stopped || node.verdict === "fail";

  return (
    <div className="rounded-md border border-node-border bg-node-fill p-lg">
      <div className="mb-md flex items-start justify-between gap-sm">
        <div>
          <div className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
            {node.kind}
          </div>
          <div
            className={`mt-2xs font-display text-h2 font-bold ${isEmber ? "text-ember" : "text-ink-light"}`}
          >
            {node.label}
          </div>
        </div>
        {node.stopped && (
          <span className="shrink-0 rounded-sm border border-ember/30 bg-ember/10 px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest text-ember">
            STOPPED
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-sm">
        <div className="rounded-sm bg-canvas px-md py-sm">
          <div className="font-mono text-micro text-neutral-faint">Baseline</div>
          <div className="tnum mt-2xs font-mono text-small font-medium text-ink-light">
            {baseVal}
          </div>
        </div>
        <div className="rounded-sm bg-canvas px-md py-sm">
          <div className="font-mono text-micro text-neutral-faint">Candidate</div>
          <div
            className={`tnum mt-2xs font-mono text-small font-medium ${isEmber ? "text-ember" : "text-ink-light"}`}
          >
            {candVal}
          </div>
        </div>
      </div>

      <div className="mt-sm border-t border-node-border pt-sm">
        <div className="flex items-center justify-between">
          <span className="font-mono text-micro text-neutral-faint">{rateLabel}</span>
          <span
            className={`tnum font-mono text-small font-bold ${isEmber ? "text-ember" : "text-verdict-pass"}`}
          >
            {baseVal} → {candVal}
          </span>
        </div>
      </div>

      {node.explanation && (
        <p className="mt-md text-small text-neutral-faint">{node.explanation}</p>
      )}

      {node.cause_file && (
        <div className="mt-md rounded-sm bg-canvas px-md py-sm">
          <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Attributed to
          </div>
          <code className="font-mono text-micro text-ink-light">{node.cause_file}</code>
        </div>
      )}

      {node.hunk && (
        <div className="mt-md overflow-x-auto rounded-sm bg-canvas p-md">
          <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Code Change
          </div>
          <pre className="font-mono text-micro leading-relaxed text-ink-light whitespace-pre-wrap">
            {node.hunk}
          </pre>
        </div>
      )}
    </div>
  );
}

// ── Overview section ──────────────────────────────────────────────────────────
export function Overview({ data }: { data: ReportData }) {
  const firstStopped = useMemo(
    () =>
      data.graph.nodes.find((n) => n.stopped) ??
      data.graph.nodes.find((n) => n.verdict === "fail") ??
      null,
    [data.graph.nodes],
  );

  const [selected, setSelected] = useState<GraphNode | null>(firstStopped);

  const baseRef = shortRef(data.meta.baseline_ref);
  const candRef = shortRef(data.meta.candidate_ref);

  return (
    <div className="space-y-2xl">
      {/* Verdict banner */}
      <VerdictBanner
        verdict={data.graph.overall_verdict}
        baseRef={baseRef}
        candRef={candRef}
      />

      {/* Stat chips */}
      <StatChips data={data} />

      {/* Graph plate + node detail */}
      <div className="grid grid-cols-1 gap-lg xl:grid-cols-[1fr_320px]">
        <GraphPlate
          data={data}
          selectedId={selected?.id ?? null}
          onSelect={setSelected}
        />
        <div className="flex flex-col gap-md">
          {selected ? (
            <NodeDetail node={selected} />
          ) : (
            <div className="flex flex-1 items-center justify-center rounded-md border border-node-border bg-node-fill p-lg text-small text-neutral-faint">
              Click a node to inspect it.
            </div>
          )}
          {/* Stopped node count callout */}
          {data.graph.nodes.filter((n) => n.stopped).length > 0 && (
            <div className="rounded-md border border-ember/20 bg-ember/5 px-md py-sm">
              <p className="text-micro text-neutral-faint">
                <span className="font-bold text-ember">
                  {data.graph.nodes.filter((n) => n.stopped).length} stopped
                </span>{" "}
                {data.graph.nodes.filter((n) => n.stopped).length === 1 ? "node" : "nodes"} detected — fired in baseline, silent in candidate.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Eval contrast */}
      {data.comparison && data.outputEvals.length > 0 && (
        <EvalContrast data={data} />
      )}
    </div>
  );
}

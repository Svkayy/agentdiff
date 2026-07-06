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
  // Verdict mapping (DESIGN.md, locked): pass = neutral/cream; warn = orange
  // outline; fail = solid orange. On the dark plate we keep fail/warn orange
  // and pass neutral cream so the states stay instantly distinguishable.
  const isEmber = verdict === "fail";
  const accentClass = isEmber
    ? "text-[#ea580c]"
    : verdict === "warn"
      ? "text-[#ea580c]"
      : "text-[#ede8dc]";
  const borderClass = isEmber
    ? "border-[#ea580c] border-2"
    : verdict === "warn"
      ? "border-[#ea580c] border-2"
      : "border-node-border border-2";

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
    <div className={`px-xl py-lg ${borderClass}`}>
      <div className="flex items-start justify-between gap-lg">
        <div>
          <h1 className={`font-mono text-display font-bold uppercase leading-tight ${accentClass}`}>
            {label}
          </h1>
          <p className="mt-xs font-mono text-body text-neutral-faint">{sub}</p>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-mono text-xs uppercase tracking-[0.2em] text-neutral-faint">Compare</div>
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
      className="relative min-w-0 overflow-x-auto overflow-y-hidden border-2 border-node-border"
      style={{ background: "#0E1116", height: "480px" }}
    >
      {/* Plate label (header-bar nameplate style) */}
      <div className="absolute left-lg top-lg z-10 flex items-center gap-sm">
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-ink-light">
          agent_graph.viz
        </span>
        <span className="border-2 border-node-border bg-node-fill px-xs py-2xs font-mono text-micro uppercase tracking-wider text-neutral-faint">
          before / after
        </span>
      </div>

      {/* React Flow fills the plate. min-w-0 on mobile lets the plate shrink
          to the viewport (no forced horizontal scroll on narrow screens);
          md:min-w-[620px] guarantees the graph stays readable at tablet+
          widths, scrolling within this plate rather than the whole page. */}
      <div className="h-full min-w-0 md:min-w-[620px]">
        <AgentGraph
          graph={data.graph}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      </div>
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
    <div className="border-2 border-node-border bg-node-fill p-lg">
      <div className="mb-md flex items-start justify-between gap-sm">
        <div>
          <div className="font-mono text-xs uppercase tracking-[0.2em] text-neutral-faint">
            {node.kind}
          </div>
          <div
            className={`mt-2xs font-mono text-h2 font-bold uppercase ${isEmber ? "text-[#ea580c]" : "text-ink-light"}`}
          >
            {node.label}
          </div>
        </div>
        {node.stopped && (
          <span className="shrink-0 border-2 border-[#ea580c] bg-[#ea580c] px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest text-background">
            STOPPED
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-sm">
        <div className="border-2 border-node-border bg-canvas px-md py-sm">
          <div className="font-mono text-xs uppercase tracking-[0.2em] text-neutral-faint">Baseline</div>
          <div className="tnum mt-2xs font-mono text-small font-bold text-ink-light">
            {baseVal}
          </div>
        </div>
        <div className="border-2 border-node-border bg-canvas px-md py-sm">
          <div className="font-mono text-xs uppercase tracking-[0.2em] text-neutral-faint">Candidate</div>
          <div
            className={`tnum mt-2xs font-mono text-small font-bold ${isEmber ? "text-[#ea580c]" : "text-ink-light"}`}
          >
            {candVal}
          </div>
        </div>
      </div>

      <div className="mt-sm border-t-2 border-node-border pt-sm">
        <div className="flex items-center justify-between">
          <span className="font-mono text-micro uppercase tracking-wider text-neutral-faint">{rateLabel}</span>
          <span
            className={`tnum font-mono text-small font-bold ${isEmber ? "text-[#ea580c]" : "text-ink-light"}`}
          >
            {baseVal} → {candVal}
          </span>
        </div>
      </div>

      {node.explanation && (
        <p className="mt-md font-mono text-small text-neutral-faint">{node.explanation}</p>
      )}

      {node.cause_file && (
        <div className="mt-md border-2 border-node-border bg-canvas px-md py-sm">
          <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-neutral-faint">
            Attributed to
          </div>
          <code className="font-mono text-micro text-ink-light">{node.cause_file}</code>
        </div>
      )}

      {node.hunk && (
        <div className="mt-md overflow-x-auto border-2 border-node-border bg-canvas p-md">
          <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-neutral-faint">
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
            <div className="flex flex-1 items-center justify-center border-2 border-node-border bg-node-fill p-lg font-mono text-small text-neutral-faint">
              Click a node to inspect it.
            </div>
          )}
          {/* Stopped node count callout */}
          {data.graph.nodes.filter((n) => n.stopped).length > 0 && (
            <div className="border-2 border-[#ea580c] bg-node-fill px-md py-sm">
              <p className="font-mono text-micro text-neutral-faint">
                <span className="font-bold text-[#ea580c]">
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

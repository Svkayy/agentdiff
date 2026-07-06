import { Handle, Position } from "@xyflow/react";
import { cn } from "@/lib/utils";
import type { GraphNode } from "@/types";

export interface NodeData extends Record<string, unknown> {
  node: GraphNode;
}

function metric(n: GraphNode): { label: string; value: string } {
  if (n.kind === "agent") {
    return {
      label: "Firing Rate",
      value: `${Math.round(n.baseline_rate * 100)}% → ${Math.round(n.candidate_rate * 100)}%`,
    };
  }
  return { label: "Avg Calls", value: `${n.baseline_rate.toFixed(1)} → ${n.candidate_rate.toFixed(1)}` };
}

export function GraphNodeCard({ data, selected }: { data: NodeData; selected: boolean }) {
  const n = data.node;
  const m = metric(n);

  // Verdict mapping (DESIGN.md, locked): pass = neutral/foreground dot;
  // warn = orange OUTLINE dot; fail = solid orange dot. Stopped agents get the
  // full solid-orange treatment below and stay THE most salient node.
  const dot = n.stopped
    ? "bg-[#ea580c]"
    : n.verdict === "warn"
      ? "border-2 border-[#ea580c] bg-transparent"
      : n.verdict === "fail"
        ? "bg-[#ea580c]"
        : "bg-[#ede8dc]";

  return (
    <div
      className={cn(
        "w-[240px] animate-fade-in border-2 p-4 font-mono",
        // Stopped = solid orange plate: the loudest thing on the graph.
        n.stopped
          ? "border-[#ea580c] bg-[#ea580c] text-background scale-[1.03] halo-glow"
          : "border-node-border bg-node-fill text-[#ede8dc]",
        selected && !n.stopped && "ring-2 ring-primary-dark/60",
        selected && n.stopped && "ring-2 ring-background/70",
        (n.hunk || n.explanation) && "cursor-pointer",
      )}
    >
      <Handle type="target" position={Position.Left} />
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className={cn("text-sm font-bold uppercase tracking-wide", n.stopped && "text-background")}>
          {n.label}
        </span>
        {n.stopped ? (
          <div className="shrink-0 border-2 border-background px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider text-background">
            STOPPED FIRING
          </div>
        ) : (
          <div className={cn("h-2.5 w-2.5 shrink-0", dot)} />
        )}
      </div>
      <div
        className={cn(
          "mt-2 flex justify-between border-t-2 pt-3 font-mono text-xs tnum",
          n.stopped ? "border-background/40" : "border-node-border",
        )}
      >
        <span className={n.stopped ? "text-background/80" : "text-neutral-faint"}>{m.label}</span>
        <span className={cn("font-bold", n.stopped ? "text-background" : "text-[#ede8dc]")}>
          {m.value}
        </span>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

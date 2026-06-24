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

  const dot = n.stopped
    ? "bg-ember"
    : n.verdict === "warn"
      ? "bg-amber-400"
      : "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]";

  return (
    <div
      className={cn(
        "w-[240px] rounded-xl p-4 animate-fade-in",
        n.stopped ? "bg-white/90 backdrop-blur-md halo-glow scale-[1.03]" : "glass-node",
        selected && !n.stopped && "ring-2 ring-primary-dark/50",
        selected && n.stopped && "ring-2 ring-ember/50",
        (n.hunk || n.explanation) && "cursor-pointer",
      )}
    >
      <Handle type="target" position={Position.Left} />
      <div className="mb-3 flex items-center justify-between">
        <span
          className={cn(
            "text-base font-semibold",
            n.stopped ? "font-bold text-ember" : "text-ink-light",
          )}
        >
          {n.label}
        </span>
        {n.stopped ? (
          <div className="rounded border border-ember/30 bg-red-50 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider text-ember">
            STOPPED FIRING
          </div>
        ) : (
          <div className={cn("h-2.5 w-2.5 rounded-full border border-white", dot)} />
        )}
      </div>
      <div
        className={cn(
          "mt-2 flex justify-between border-t pt-3 font-mono text-xs tnum",
          n.stopped ? "border-ember/20" : "border-node-border",
        )}
      >
        <span className="text-neutral-faint">{m.label}</span>
        <span className={cn("font-medium", n.stopped ? "font-bold text-ember" : "text-ink-light")}>
          {m.value}
        </span>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

import type { AgentGraph, Verdict } from "@/types";

function Chip({ label, accent }: { label: string; accent?: boolean }) {
  return (
    <span
      className={
        accent
          ? "rounded border border-red-200 bg-red-50 px-2 py-0.5 font-medium text-ember shadow-sm"
          : "rounded border border-slate-200 bg-white px-2 py-0.5 text-slate-600 shadow-sm"
      }
    >
      {label}
    </span>
  );
}

export function Footer({ graph, verdict }: { graph: AgentGraph; verdict: Verdict }) {
  const agents = graph.nodes.filter((n) => n.kind === "agent").length;
  const tools = graph.nodes.filter((n) => n.kind !== "agent").length;
  const stopped = graph.nodes.filter((n) => n.stopped).length;

  return (
    <footer className="glass-panel z-50 flex h-10 w-full shrink-0 items-center justify-between border-t border-slate-200 px-6 font-mono text-xs text-slate-500">
      <div className="flex items-center gap-4">
        <span className="font-semibold text-slate-600">AgentDiff</span>
        <div className="h-4 w-px bg-slate-300" />
        <div className="flex gap-2">
          <Chip label={`Agents: ${agents}`} />
          <Chip label={`Tools: ${tools}`} />
          <Chip label={`Stopped: ${stopped}`} accent={stopped > 0} />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span
          className={
            verdict === "fail"
              ? "rounded border border-red-200 bg-red-100 px-2 py-0.5 font-bold text-red-800 shadow-sm"
              : verdict === "warn"
                ? "rounded border border-amber-200 bg-amber-50 px-2 py-0.5 font-bold text-amber-700 shadow-sm"
                : "rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-bold text-emerald-700 shadow-sm"
          }
        >
          Status: {verdict === "fail" ? "REGRESSION" : verdict === "warn" ? "WARN" : "CLEAN"}
        </span>
      </div>
    </footer>
  );
}

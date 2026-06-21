import { cn } from "@/lib/utils";
import type { GraphNode } from "@/types";

const TABS = [
  { key: "nodes", label: "Nodes", icon: "account_tree" },
  { key: "errors", label: "Errors", icon: "error" },
  { key: "diffs", label: "Diffs", icon: "difference" },
  { key: "traces", label: "Traces", icon: "history" },
  { key: "logs", label: "Logs", icon: "terminal" },
];

function DiffHunk({ hunk }: { hunk: string }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white font-mono text-[11px] leading-[1.8] shadow-sm">
      {hunk.split("\n").map((line, i) => {
        const added = line.startsWith("+");
        const removed = line.startsWith("-");
        return (
          <div
            key={i}
            className={cn(
              "flex items-start px-3 py-1.5",
              removed && "bg-red-50/50 text-red-900",
              added && "bg-emerald-50/50 text-emerald-900",
              !added && !removed && "text-slate-500",
            )}
          >
            <span className="w-5 shrink-0 select-none pr-2 text-right text-slate-400">
              {added ? "+" : removed ? "-" : ""}
            </span>
            <span className="whitespace-pre-wrap break-all">{line.replace(/^[+-]/, "")}</span>
          </div>
        );
      })}
    </div>
  );
}

export function Inspector({ node }: { node: GraphNode | null }) {
  return (
    <aside className="glass-panel z-40 flex h-full w-[340px] shrink-0 flex-col border-l border-slate-200">
      {/* Header */}
      <div className="flex shrink-0 flex-col gap-3 border-b border-slate-200 bg-white/40 p-5">
        <div className="flex items-center justify-between">
          <h2 className="m-0 text-xl font-bold text-slate-800">{node ? node.label : "Inspector"}</h2>
          {node?.stopped && (
            <div className="rounded border border-ember/30 bg-red-50 px-2 py-0.5 font-mono text-[10px] font-bold tracking-wider text-ember">
              REGRESSION
            </div>
          )}
        </div>
        {node?.cause_file && (
          <div className="flex items-center gap-2 font-mono text-xs text-text-muted">
            <span className="material-symbols-outlined text-[14px]">description</span>
            {node.cause_file}
          </div>
        )}
      </div>

      {/* Tabs (Diffs active; others are forthcoming surfaces) */}
      <div className="flex shrink-0 border-b border-slate-200 bg-white/60">
        {TABS.map((t) => {
          const active = t.key === "diffs";
          return (
            <div
              key={t.key}
              title={active ? undefined : "Coming soon"}
              className={cn(
                "flex flex-1 cursor-default flex-col items-center gap-1 py-2.5 text-center",
                active
                  ? "border-b-2 border-primary-dark bg-blue-50/30 font-semibold text-primary-dark"
                  : "text-text-muted/60",
              )}
            >
              <span className="material-symbols-outlined text-[16px]">{t.icon}</span>
              <span className="text-[10px] font-medium">{t.label}</span>
            </div>
          );
        })}
      </div>

      {/* Content */}
      <div className="flex flex-1 flex-col gap-6 overflow-y-auto bg-white/20 p-5">
        {!node ? (
          <p className="text-sm text-text-muted">Select a node in the graph to inspect it.</p>
        ) : (
          <>
            <div>
              <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Explanation
              </h3>
              <p className="rounded-lg border border-slate-100 bg-white/60 p-3 text-sm leading-relaxed text-slate-700 shadow-sm">
                {node.explanation ??
                  (node.stopped
                    ? `${node.label} stopped firing in the candidate.`
                    : "No behavioral change attributed to this node.")}
              </p>
            </div>

            {node.hunk ? (
              <div>
                <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Prompt Diff
                </h3>
                <DiffHunk hunk={node.hunk} />
              </div>
            ) : node.cause_file ? (
              <p className="text-xs text-text-muted">
                No diff hunk available (attribution ran without an API key).
              </p>
            ) : null}
          </>
        )}
      </div>

      {/* Footer action */}
      <div className="shrink-0 border-t border-slate-200 bg-white/40 p-5">
        <button className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition-all hover:border-slate-400 hover:bg-slate-50">
          Export Trace
        </button>
      </div>
    </aside>
  );
}

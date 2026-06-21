import type { GraphNode } from "@/types";

export function AIExplainer({ node }: { node: GraphNode | null }) {
  const text =
    node?.explanation ??
    (node?.stopped
      ? `${node.label} stopped firing in the candidate run.`
      : "Select a changed node to see what AgentDiff attributes the behavioral change to.");

  return (
    <div className="glass-panel absolute bottom-6 left-6 z-40 flex w-[340px] flex-col overflow-hidden rounded-xl border border-slate-200 shadow-xl">
      <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50/80 px-4 py-2.5 backdrop-blur">
        <span className="material-symbols-outlined text-sm text-primary-dark">auto_awesome</span>
        <span className="text-xs font-semibold text-slate-700">AI Assistant Insights</span>
      </div>
      <div className="bg-white/60 p-4">
        <div className="flex items-start gap-3">
          <div className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-primary-dark/20 bg-primary-dark/10">
            <span className="material-symbols-outlined text-[14px] text-primary-dark">smart_toy</span>
          </div>
          <div className="rounded-lg rounded-tl-none border border-slate-100 bg-slate-50 p-3 text-sm leading-relaxed text-slate-700 shadow-sm">
            <p>{text}</p>
            {node?.cause_file && (
              <p className="mt-2">
                Source:{" "}
                <span className="rounded bg-red-50 px-1 font-mono text-xs text-red-600">
                  {node.cause_file}
                </span>
              </p>
            )}
          </div>
        </div>
      </div>
      <div className="border-t border-slate-100 bg-white/80 p-2">
        <div className="relative">
          <input
            type="text"
            disabled
            placeholder="Ask about this regression… (coming soon)"
            className="w-full cursor-not-allowed rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-700 placeholder-slate-400 focus:outline-none"
          />
          <button
            disabled
            className="absolute right-2 top-1.5 cursor-not-allowed text-slate-300"
            aria-label="Send (coming soon)"
          >
            <span className="material-symbols-outlined text-[18px]">send</span>
          </button>
        </div>
      </div>
    </div>
  );
}

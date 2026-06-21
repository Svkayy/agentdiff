import type { AgentGraph } from "@/types";

/**
 * Low-sample trust signal. When a flagged change isn't statistically confirmed
 * at the captured sample size, say so plainly — a single run per side can look
 * like a regression by chance. Protects against false confidence.
 */
export function TrustBanner({ graph }: { graph: AgentGraph }) {
  if (!graph.has_uncertain) return null;
  const n = graph.min_samples;
  const runs = n === 1 ? "1 run" : `${n} runs`;
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-amber-200 bg-amber-50/80 px-6 py-2 text-xs text-[#92600a] backdrop-blur">
      <span className="material-symbols-outlined text-[16px]">info</span>
      <span>
        Based on <span className="font-mono font-semibold tnum">{runs}</span> per side — some
        changes aren't statistically confirmed at this sample size. Capture more runs to be sure.
      </span>
    </div>
  );
}

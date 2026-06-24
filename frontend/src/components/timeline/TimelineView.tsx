import { EventRow } from "@/components/timeline/EventRow";
import type { TrajectorySummary } from "@/types";

interface TimelineViewProps {
  trajectory: TrajectorySummary;
  side: "baseline" | "candidate";
}

export function TimelineView({ trajectory, side }: TimelineViewProps) {
  const { timeline } = trajectory;

  // Collect unique agents present in this trajectory
  const agentsPresent = [
    ...new Set(
      timeline
        .map((e) => e.inferred_agent)
        .filter((a): a is string => a !== null),
    ),
  ];

  const llmCalls = timeline.filter(
    (e) => e.kind === "llm_request" || e.kind === "llm_response",
  ).length;
  const toolCalls = timeline.filter((e) => e.kind === "local_tool_invoked").length;

  return (
    <div className="space-y-md">
      {/* Summary bar */}
      <div className="flex flex-wrap items-center gap-md rounded-sm border border-node-border bg-node-fill px-md py-sm">
        <div className="font-mono text-micro text-neutral-faint">
          <span className="text-ink-light">{timeline.length}</span> events
        </div>
        <div className="font-mono text-micro text-neutral-faint">
          <span className="text-ink-light">{llmCalls}</span> LLM calls
        </div>
        <div className="font-mono text-micro text-neutral-faint">
          <span className="text-ink-light">{toolCalls}</span> tool calls
        </div>
        <div className="ml-auto flex flex-wrap gap-xs">
          {agentsPresent.map((a) => (
            <span
              key={a}
              className="rounded-sm border border-node-border bg-canvas px-xs py-2xs font-mono text-micro text-ink-light"
            >
              {a}
            </span>
          ))}
        </div>
        {side === "candidate" && !agentsPresent.includes("fact_checker") && (
          <span className="rounded-sm border border-ember/30 bg-ember/10 px-xs py-2xs font-mono text-micro text-ember">
            fact_checker absent
          </span>
        )}
      </div>

      {/* Event rows */}
      <div className="space-y-2xs">
        {timeline.map((event) => (
          <EventRow key={`${event.seq}-${event.kind}`} event={event} />
        ))}
      </div>
    </div>
  );
}

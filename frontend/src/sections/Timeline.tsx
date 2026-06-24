import { useState } from "react";
import { TimelineView } from "@/components/timeline/TimelineView";
import type { ReportData, TrajectorySummary } from "@/types";

// ── Case + side selector ──────────────────────────────────────────────────────
type Side = "baseline" | "candidate";

function getTestCaseIds(data: ReportData): string[] {
  const ids = new Set<string>();
  for (const t of [...data.trajectories.baseline, ...data.trajectories.candidate]) {
    ids.add(t.test_case_id);
  }
  return [...ids];
}

function firstTrajForCase(
  trajectories: TrajectorySummary[],
  testCaseId: string,
): TrajectorySummary | null {
  return trajectories.find((t) => t.test_case_id === testCaseId) ?? null;
}

export function Timeline({ data }: { data: ReportData }) {
  const caseIds = getTestCaseIds(data);
  const [activeCaseId, setActiveCaseId] = useState<string>(caseIds[0] ?? "");
  const [side, setSide] = useState<Side>("baseline");

  if (caseIds.length === 0) {
    return (
      <div className="space-y-lg">
        <h1 className="font-display text-h1 font-bold text-ink-light">Trajectory Timeline</h1>
        <p className="text-small text-neutral-faint">No trajectory data in this run.</p>
      </div>
    );
  }

  const trajectoryList =
    side === "baseline" ? data.trajectories.baseline : data.trajectories.candidate;
  const traj = firstTrajForCase(trajectoryList, activeCaseId);

  return (
    <div className="space-y-xl">
      <div>
        <h1 className="font-display text-h1 font-bold text-ink-light">Trajectory Timeline</h1>
        <p className="mt-xs text-small text-neutral-faint">
          Step-by-step event log for a single trajectory. The candidate side is missing the{" "}
          <code className="font-mono text-small text-ink-light">fact_checker</code> LLM calls and
          tool calls present in baseline.
        </p>
      </div>

      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-md">
        {/* Test case tabs */}
        <div className="flex gap-xs border-b border-node-border">
          {caseIds.map((id) => (
            <button
              key={id}
              onClick={() => setActiveCaseId(id)}
              className={`px-md py-sm font-mono text-small transition-colors duration-[80ms] ${
                activeCaseId === id
                  ? "border-b-2 border-ink-light text-ink-light -mb-px"
                  : "text-neutral-faint hover:text-ink-light"
              }`}
            >
              {id}
            </button>
          ))}
        </div>

        {/* Side toggle */}
        <div className="ml-auto flex rounded-sm border border-node-border overflow-hidden">
          {(["baseline", "candidate"] as Side[]).map((s) => (
            <button
              key={s}
              onClick={() => setSide(s)}
              className={`px-md py-sm font-mono text-small transition-colors duration-[80ms] ${
                side === s
                  ? "bg-node-fill text-ink-light"
                  : "text-neutral-faint hover:bg-node-fill/50 hover:text-ink-light"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Regression callout when viewing candidate */}
      {side === "candidate" && (
        <div className="rounded-md border border-ember/20 bg-ember/5 px-md py-sm">
          <p className="text-small text-neutral-faint">
            <span className="font-bold text-ember">Regression visible:</span> this candidate
            trajectory has fewer events because{" "}
            <code className="font-mono text-ember">fact_checker</code> stopped firing — compare
            with baseline to see the missing LLM calls and tool invocations.
          </p>
        </div>
      )}

      {/* Timeline view */}
      {traj ? (
        <TimelineView trajectory={traj} side={side} />
      ) : (
        <div className="rounded-md border border-node-border bg-node-fill px-lg py-2xl text-center">
          <p className="text-small text-neutral-faint">
            No trajectory found for{" "}
            <code className="font-mono text-small text-ink-light">{activeCaseId}</code> ({side}).
          </p>
        </div>
      )}
    </div>
  );
}

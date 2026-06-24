import type { ReportData, Verdict } from "@/types";

function VerdictBadge({ verdict, dim }: { verdict: Verdict; dim?: boolean }) {
  const base = "inline-flex items-center rounded-sm px-xs py-2xs font-mono text-micro font-bold uppercase tracking-widest";
  if (verdict === "fail") {
    return (
      <span className={`${base} ${dim ? "bg-ember/8 text-ember/50" : "bg-ember/15 text-ember border border-ember/30"}`}>
        FAIL
      </span>
    );
  }
  if (verdict === "warn") {
    return (
      <span className={`${base} ${dim ? "bg-verdict-warn/8 text-verdict-warn/50" : "bg-verdict-warn/15 text-verdict-warn border border-verdict-warn/30"}`}>
        WARN
      </span>
    );
  }
  return (
    <span className={`${base} ${dim ? "bg-verdict-pass/8 text-verdict-pass/50" : "bg-verdict-pass/15 text-verdict-pass border border-verdict-pass/30"}`}>
      PASS
    </span>
  );
}

export function EvalContrast({ data }: { data: ReportData }) {
  const tcs = data.comparison?.test_case_comparisons ?? [];
  const evalMap = new Map(data.outputEvals.map((e) => [e.test_case_id, e.verdict]));

  // Build rows: for each test case, pair output-eval verdict with behavioral verdict
  const rows = tcs.map((tc) => ({
    id: tc.test_case_id,
    outputVerdict: evalMap.get(tc.test_case_id) ?? null,
    behavioralVerdict: tc.overall_verdict,
  }));

  // A row is the "key insight" when output-eval says pass/warn but behavioral is fail
  const isTradMiss = (outputV: Verdict | null, behavV: Verdict) =>
    behavV === "fail" && (outputV === "pass" || outputV === null);

  return (
    <div className="rounded-lg border border-node-border bg-node-fill">
      {/* Header */}
      <div className="border-b border-node-border px-lg py-md">
        <h3 className="font-display text-h2 font-semibold text-ink-light">
          Output Eval vs AgentDiff
        </h3>
        <p className="mt-xs text-small text-neutral-faint">
          Traditional output-eval misses what behavioral comparison catches.
        </p>
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-[1fr_auto_auto] gap-md border-b border-node-border px-lg py-sm">
        <span className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
          Test Case
        </span>
        <span className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
          Output Eval
        </span>
        <span className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
          AgentDiff
        </span>
      </div>

      {/* Rows */}
      {rows.map((row) => {
        const highlight = isTradMiss(row.outputVerdict, row.behavioralVerdict);
        return (
          <div
            key={row.id}
            className={`grid grid-cols-[1fr_auto_auto] items-center gap-md px-lg py-md transition-colors ${
              highlight
                ? "border-l-2 border-ember bg-ember/5"
                : "border-l-2 border-transparent"
            }`}
          >
            <span className="font-mono text-small text-ink-light">{row.id}</span>
            <span className="flex justify-end">
              {row.outputVerdict ? (
                <VerdictBadge verdict={row.outputVerdict} dim={highlight} />
              ) : (
                <span className="font-mono text-micro text-neutral-faint">—</span>
              )}
            </span>
            <span className="flex justify-end">
              <VerdictBadge verdict={row.behavioralVerdict} />
            </span>
          </div>
        );
      })}

      {/* Legend */}
      {rows.some((r) => isTradMiss(r.outputVerdict, r.behavioralVerdict)) && (
        <div className="border-t border-node-border px-lg py-md">
          <p className="text-micro text-neutral-faint">
            <span className="mr-xs inline-block h-2 w-2 rounded-full bg-ember align-middle" />
            Highlighted rows: output eval passed while AgentDiff detected a behavioral regression.
          </p>
        </div>
      )}
    </div>
  );
}

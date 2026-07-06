import { verdictLabel } from "@/pages/ProjectPage";
import type { ReportData, Verdict } from "@/types";

// Verdict mapping (DESIGN.md, locked): pass = neutral cream chip; warn = orange
// outline; fail = solid orange. `dim` softens a chip that is being contrasted
// against the AgentDiff column.
function VerdictBadge({ verdict, dim }: { verdict: Verdict; dim?: boolean }) {
  const base = "inline-flex items-center px-xs py-2xs font-mono text-micro font-bold uppercase tracking-widest";
  if (verdict === "fail") {
    return (
      <span className={`${base} border-2 border-[#ea580c] bg-[#ea580c] ${dim ? "text-background/60" : "text-background"}`}>
        {verdictLabel(verdict)}
      </span>
    );
  }
  if (verdict === "warn") {
    return (
      <span className={`${base} border-2 border-[#ea580c] ${dim ? "text-[#ea580c]/50" : "text-[#ea580c]"}`}>
        {verdictLabel(verdict)}
      </span>
    );
  }
  return (
    <span className={`${base} border-2 border-node-border ${dim ? "text-neutral-faint" : "text-ink-light"}`}>
      {verdictLabel(verdict)}
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
    <div className="border-2 border-node-border bg-node-fill">
      {/* Header-bar nameplate */}
      <div className="border-b-2 border-node-border px-lg py-md">
        <h3 className="font-mono text-h2 font-bold uppercase text-ink-light">
          Output Eval vs AgentDiff
        </h3>
        <p className="mt-xs font-mono text-small text-neutral-faint">
          Traditional output-eval misses what behavioral comparison catches.
        </p>
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-[1fr_auto_auto] gap-md border-b-2 border-node-border px-lg py-sm">
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-neutral-faint">
          Test Case
        </span>
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-neutral-faint">
          Output Eval
        </span>
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-neutral-faint">
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
                ? "border-l-2 border-[#ea580c] bg-[#ea580c]/10"
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
        <div className="border-t-2 border-node-border px-lg py-md">
          <p className="font-mono text-micro text-neutral-faint">
            <span className="mr-xs inline-block h-2 w-2 bg-[#ea580c] align-middle" />
            Highlighted rows: output eval passed while AgentDiff detected a behavioral change.
          </p>
        </div>
      )}
    </div>
  );
}

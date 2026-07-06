import { countFlaggedDeltas } from "@/lib/payload";
import type { ReportData, Verdict } from "@/types";

function Chip({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent?: "ember" | "pass" | "warn";
}) {
  // Verdict mapping (DESIGN.md, locked): fail/warn = orange signal; pass and
  // neutral stats = cream (no color signal) so the orange stays meaningful.
  const accentClass =
    accent === "ember"
      ? "text-[#ea580c]"
      : accent === "warn"
        ? "text-[#ea580c]"
        : "text-ink-light";

  return (
    <div className="flex flex-col gap-2xs border-2 border-node-border bg-node-fill px-lg py-md">
      <span className="font-mono text-xs uppercase tracking-[0.2em] text-neutral-faint">
        {label}
      </span>
      <span className={`tnum font-mono text-h2 font-bold ${accentClass}`}>{value}</span>
    </div>
  );
}

function verdictAccent(v: Verdict): "ember" | "pass" | "warn" {
  return v === "fail" ? "ember" : v === "warn" ? "warn" : "pass";
}

export function StatChips({ data }: { data: ReportData }) {
  const verdict = data.graph.overall_verdict;
  const flagged = countFlaggedDeltas(data);
  const samples =
    data.meta.samples_per_case != null ? String(data.meta.samples_per_case) : "—";

  // Use first test case behavioral_overlap as representative (or average if multiple)
  const tcs = data.comparison?.test_case_comparisons ?? [];
  const overlaps = tcs
    .map((tc) => tc.behavioral_overlap)
    .filter((v): v is number => v !== null && v !== undefined);
  const avgOverlap =
    overlaps.length > 0
      ? Math.round((overlaps.reduce((a, b) => a + b, 0) / overlaps.length) * 100)
      : null;

  // Runtime metric deltas (latency/tokens/error-rate — Task 7/8) flagged non-pass.
  const runMetrics = tcs.flatMap((tc) => tc.run_metrics ?? []);
  const flaggedRunMetrics = runMetrics.filter((m) => m.verdict !== "pass").length;
  const lowPowerCount = data.warnings.length;

  return (
    <div className="grid grid-cols-2 gap-md sm:grid-cols-4">
      <Chip
        label="Verdict"
        value={verdict.toUpperCase()}
        accent={verdictAccent(verdict)}
      />
      <Chip
        label="Flagged Deltas"
        value={flagged}
        accent={flagged > 0 ? "ember" : "pass"}
      />
      <Chip label="Samples / Side" value={samples} />
      {/* Behavioral overlap is a neutral statistic, not a regression signal.
          Use neutral ink regardless of value — ember is reserved for stopped nodes. */}
      <Chip
        label="Behavioral Overlap"
        value={avgOverlap !== null ? `${avgOverlap}%` : "—"}
      />
      {runMetrics.length > 0 && (
        <Chip
          label="Runtime Metric Flags"
          value={flaggedRunMetrics}
          accent={flaggedRunMetrics > 0 ? "ember" : "pass"}
        />
      )}
      {lowPowerCount > 0 && (
        <Chip label="Low-Power Warnings" value={lowPowerCount} accent="warn" />
      )}
    </div>
  );
}

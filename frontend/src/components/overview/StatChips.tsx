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
  const accentClass =
    accent === "ember"
      ? "text-ember"
      : accent === "pass"
        ? "text-verdict-pass"
        : accent === "warn"
          ? "text-verdict-warn"
          : "text-ink-light";

  return (
    <div className="flex flex-col gap-2xs rounded-md border border-node-border bg-node-fill px-lg py-md">
      <span className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
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
      <Chip
        label="Behavioral Overlap"
        value={avgOverlap !== null ? `${avgOverlap}%` : "—"}
        accent={
          avgOverlap !== null
            ? avgOverlap >= 80
              ? "pass"
              : avgOverlap >= 60
                ? "warn"
                : "ember"
            : undefined
        }
      />
    </div>
  );
}

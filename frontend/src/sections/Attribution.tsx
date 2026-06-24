import type { ReportData } from "@/types";

export function Attribution({ data: _data }: { data: ReportData }) {
  return (
    <div className="space-y-lg">
      <h1 className="font-display text-h1 font-bold text-ink-light">Causal Attribution</h1>
      <p className="text-small text-neutral-faint">Populated in the next pass.</p>
    </div>
  );
}

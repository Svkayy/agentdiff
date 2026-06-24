import type { ReportData } from "@/types";

export function Timeline({ data: _data }: { data: ReportData }) {
  return (
    <div className="space-y-lg">
      <h1 className="font-display text-h1 font-bold text-ink-light">Trajectory Timeline</h1>
      <p className="text-small text-neutral-faint">Populated in the next pass.</p>
    </div>
  );
}

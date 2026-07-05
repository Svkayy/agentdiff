import { dedupeAttributions } from "@/lib/payload";
import { AttributionCard } from "@/components/attribution/AttributionCard";
import type { ReportData } from "@/types";

export function Attribution({ data }: { data: ReportData }) {
  const raw = data.attribution?.attributions ?? [];
  const entries = dedupeAttributions(raw);

  if (!data.attribution || entries.length === 0) {
    return (
      <div className="space-y-lg">
        <h1 className="font-display text-h1 font-bold text-ink-light">Causal Attribution</h1>
        <div className="rounded-md border border-node-border bg-node-fill px-lg py-2xl text-center">
          <p className="text-small text-neutral-faint">
            No attribution data in this run. Attribution requires at least one non-passing
            behavioral delta.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-xl">
      <div>
        <h1 className="font-display text-h1 font-bold text-ink-light">Causal Attribution</h1>
        <p className="mt-xs text-small text-neutral-faint">
          Each non-passing behavioral delta mapped to the specific changed file (and diff hunk) most
          likely responsible. One card per agent, highest-confidence cause shown.
        </p>
      </div>

      <div className="space-y-lg">
        {entries.map((entry) => (
          <AttributionCard key={entry.agent_name} entry={entry} />
        ))}
      </div>

      {/* Footer note */}
      <p className="text-micro text-neutral-faint">
        Weight = normalized causal score assigned by the attribution engine. Confidence label
        (high / medium / low) reflects how strong the underlying rule match was — a
        &quot;low-confidence heuristic&quot; cause is a best guess, not a confirmed root cause.
        Primary cause shown; alternatives listed within each card.
      </p>
    </div>
  );
}

import { Badge } from "@/components/ui/badge";
import { CardSpotlight } from "@/components/aceternity/CardSpotlight";
import { DiffHunk } from "@/components/attribution/DiffHunk";
import type { AttributionConfidence, AttributionEntry, Verdict } from "@/types";

// Verdict mapping (DESIGN.md, locked): pass = neutral cream; warn = orange
// OUTLINE; fail = solid orange.
function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const styles: Record<Verdict, string> = {
    fail: "border-[#ea580c] bg-[#ea580c] text-background",
    warn: "border-[#ea580c] text-[#ea580c]",
    pass: "border-node-border text-ink-light",
  };
  return (
    <Badge
      className={`rounded-none border-2 font-mono text-micro font-bold uppercase tracking-widest ${styles[verdict]}`}
      variant="outline"
    >
      {verdict}
    </Badge>
  );
}

// Normalize verdict string from the engine (may be lowercase)
function asVerdict(v: string): Verdict {
  const lower = v.toLowerCase();
  if (lower === "pass" || lower === "warn" || lower === "fail") return lower as Verdict;
  return "fail";
}

// Confidence label shown alongside the numeric weight — "low" is called out
// explicitly as a heuristic guess rather than a confirmed cause.
function confidenceLabel(confidence: AttributionConfidence): string {
  if (confidence === "high") return "high confidence";
  if (confidence === "medium") return "medium confidence";
  return "low-confidence heuristic";
}

// Confidence is styled mono/uppercase; low-confidence heuristics get the orange
// outline treatment so a best-guess cause is visually flagged, high/medium are
// neutral cream (a confident cause needs no signal).
function ConfidenceBadge({ confidence }: { confidence: AttributionConfidence }) {
  const styles: Record<AttributionConfidence, string> = {
    high: "border-node-border text-ink-light",
    medium: "border-node-border text-neutral-faint",
    low: "border-[#ea580c] text-[#ea580c]",
  };
  return (
    <span
      className={`border-2 px-xs py-2xs font-mono text-micro uppercase tracking-widest ${styles[confidence]}`}
    >
      {confidenceLabel(confidence)}
    </span>
  );
}

export function AttributionCard({ entry }: { entry: AttributionEntry }) {
  const verdict = asVerdict(entry.verdict);
  const primary = entry.primary;
  const confidencePct = primary ? Math.round(primary.weight * 100) : null;

  return (
    <CardSpotlight className="border-2 border-node-border bg-node-fill p-lg space-y-md">
      {/* Card header */}
      <div className="flex items-start justify-between gap-md">
        <div>
          <div className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Agent
          </div>
          <div
            className={`mt-2xs font-mono text-h2 font-bold uppercase ${
              verdict === "fail" ? "text-[#ea580c]" : "text-ink-light"
            }`}
          >
            {entry.agent_name}
          </div>
          <div className="mt-xs font-mono text-small text-neutral-faint">
            {entry.delta_summary}
          </div>
        </div>
        <VerdictBadge verdict={verdict} />
      </div>

      {/* Primary cause */}
      {primary && (
        <div className="space-y-sm">
          <div className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Primary Cause
          </div>
          <div className="border-2 border-node-border bg-canvas px-md py-sm space-y-2xs">
            <div className="flex items-center gap-sm flex-wrap">
              <code className="font-mono text-small text-ink-light">{primary.target_path}</code>
              <span className="border-2 border-node-border bg-node-fill px-xs py-2xs font-mono text-micro text-neutral-faint">
                {primary.rule}
              </span>
              <span className="font-mono text-small font-bold text-ink-light">
                {confidencePct}% weight
              </span>
              <ConfidenceBadge confidence={primary.confidence} />
            </div>
            <p className="text-small text-neutral-faint">{primary.reason}</p>
          </div>

          {/* Diff hunk */}
          {primary.hunk && (
            <div>
              <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
                Code Change
              </div>
              <DiffHunk hunk={primary.hunk} />
            </div>
          )}
        </div>
      )}

      {/* Explanation */}
      {entry.explanation && (
        <div className="border-l-2 border-neutral-muted pl-md">
          <p className="text-small italic text-neutral-faint leading-relaxed">
            {entry.explanation}
          </p>
        </div>
      )}

      {/* Alternatives */}
      {entry.alternatives.length > 0 && (
        <div className="space-y-xs">
          <div className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Alternatives Considered
          </div>
          <div className="space-y-2xs">
            {entry.alternatives.map((alt, i) => (
              <div
                key={i}
                className="flex items-center gap-sm flex-wrap border-2 border-node-border bg-canvas px-md py-sm"
              >
                <code className="font-mono text-micro text-ink-light">{alt.target_path}</code>
                <span className="font-mono text-micro text-neutral-faint">{alt.rule}</span>
                <span className="font-mono text-micro font-bold text-neutral-faint">
                  {Math.round(alt.weight * 100)}%
                </span>
                <ConfidenceBadge confidence={alt.confidence} />
              </div>
            ))}
          </div>
        </div>
      )}
    </CardSpotlight>
  );
}

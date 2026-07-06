import { useState } from "react";
import { useReportData } from "@/lib/payload";
import { cn } from "@/lib/utils";
import type { ReportData } from "@/types";
import { Overview } from "@/sections/Overview";
import { BehavioralDeltas } from "@/sections/BehavioralDeltas";
import { Attribution } from "@/sections/Attribution";
import { Timeline } from "@/sections/Timeline";
import { RunSummary } from "@/sections/RunSummary";

// ── Rigor banners: low-power warnings + eval-incomplete skipped checks ───────
// (Mirrors RunDetailPage's banners; the CLI dashboard has no run header.)
function RigorBanners({ data }: { data: ReportData }) {
  const skippedCount = data.outputEvals.reduce(
    (n, e) => n + e.skipped_checks.length,
    0,
  );
  if (data.warnings.length === 0 && skippedCount === 0) return null;

  return (
    <div className="mb-xl space-y-sm">
      {data.warnings.length > 0 && (
        <div className="rounded-md border border-verdict-warn/30 bg-verdict-warn/5 px-lg py-md">
          <div className="mb-xs font-mono text-micro font-bold uppercase tracking-widest text-verdict-warn">
            Low statistical power
          </div>
          <ul className="list-inside list-disc space-y-2xs text-small text-ink-dark">
            {data.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      {skippedCount > 0 && (
        <div className="rounded-md border border-verdict-warn/30 bg-verdict-warn/5 px-lg py-md">
          <div className="mb-xs font-mono text-micro font-bold uppercase tracking-widest text-verdict-warn">
            Evaluation incomplete
          </div>
          <ul className="list-inside list-disc space-y-2xs text-small text-ink-dark">
            {data.outputEvals.flatMap((e) =>
              e.skipped_checks.map((s, i) => (
                <li key={`${e.test_case_id}-${s.check}-${i}`}>
                  <code className="font-mono text-micro">{e.test_case_id}</code>: {s.check}{" "}
                  skipped — {s.reason}
                </li>
              )),
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "deltas", label: "Behavioral Deltas" },
  { id: "attribution", label: "Attribution" },
  { id: "timeline", label: "Timeline" },
  { id: "summary", label: "Summary" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function TabBar({
  active,
  onChange,
}: {
  active: TabId;
  onChange: (id: TabId) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Run report sections"
      className="flex flex-wrap gap-xs border-b border-hairline"
    >
      {TABS.map((tab) => {
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls={`panel-${tab.id}`}
            id={`tab-${tab.id}`}
            onClick={() => onChange(tab.id)}
            className={cn(
              "rounded-t-sm px-md py-sm font-mono text-small transition-colors duration-[80ms] -mb-px",
              isActive
                ? "border-b-2 border-ink-dark text-ink-dark"
                : "text-neutral-faint hover:text-ink-dark",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Standalone local report dashboard for the CLI single-file build. Consumes the
 * injected `window.__AGENTDIFF__` payload via useReportData(). No router, no
 * Clerk — self-contained, works offline.
 */
export function CliReport() {
  const data = useReportData();
  const [active, setActive] = useState<TabId>("overview");

  return (
    <div className="mx-auto w-full max-w-[1240px] px-xl py-2xl">
      <div className="mb-xl">
        <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
          AgentDiff report
        </div>
        <h1 className="font-display text-h1 font-bold text-ink-dark">
          Behavioral diff
        </h1>
      </div>
      <TabBar active={active} onChange={setActive} />
      <RigorBanners data={data} />
      <div
        role="tabpanel"
        id={`panel-${active}`}
        aria-labelledby={`tab-${active}`}
        className="rounded-lg border border-node-border p-xl"
        style={{ background: "#0E1116" }}
      >
        {active === "overview" && <Overview data={data} />}
        {active === "deltas" && <BehavioralDeltas data={data} />}
        {active === "attribution" && <Attribution data={data} />}
        {active === "timeline" && <Timeline data={data} />}
        {active === "summary" && <RunSummary data={data} />}
      </div>
    </div>
  );
}

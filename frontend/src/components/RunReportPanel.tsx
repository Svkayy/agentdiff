import { useState } from "react";
import { cn } from "@/lib/utils";
import type { ReportData } from "@/types";
import { Overview } from "@/sections/Overview";
import { BehavioralDeltas } from "@/sections/BehavioralDeltas";
import { Attribution } from "@/sections/Attribution";
import { Timeline } from "@/sections/Timeline";
import { RunSummary } from "@/sections/RunSummary";

function RigorBanners({ data }: { data: ReportData }) {
  const skippedCount = data.outputEvals.reduce((n, e) => n + e.skipped_checks.length, 0);
  if (data.warnings.length === 0 && skippedCount === 0) return null;

  return (
    <div className="mb-xl mt-xl space-y-sm">
      {data.warnings.length > 0 && (
        <div className="border-2 border-[#ea580c] bg-background px-lg py-md">
          <div className="mb-xs font-mono text-xs font-bold uppercase tracking-[0.2em] text-[#ea580c]">
            Low statistical power
          </div>
          <ul className="list-inside list-disc space-y-2xs font-mono text-small text-foreground">
            {data.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      {skippedCount > 0 && (
        <div className="border-2 border-[#ea580c] bg-background px-lg py-md">
          <div className="mb-xs font-mono text-xs font-bold uppercase tracking-[0.2em] text-[#ea580c]">
            Evaluation incomplete
          </div>
          <ul className="list-inside list-disc space-y-2xs font-mono text-small text-foreground">
            {data.outputEvals.flatMap((e) =>
              e.skipped_checks.map((s, i) => (
                <li key={`${e.test_case_id}-${s.check}-${i}`}>
                  <code className="font-mono text-micro">{e.test_case_id}</code>: {s.check} skipped
                  - {s.reason}
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
  { id: "overview", label: "Overview", file: "overview.sys" },
  { id: "deltas", label: "Behavioral Deltas", file: "behavioral_deltas.log" },
  { id: "attribution", label: "Attribution", file: "attribution.map" },
  { id: "timeline", label: "Timeline", file: "trajectory.log" },
  { id: "summary", label: "Summary", file: "run_summary.md" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function TabBar({ active, onChange }: { active: TabId; onChange: (id: TabId) => void }) {
  return (
    <div
      role="tablist"
      aria-label="Run report sections"
      className="flex flex-wrap border-2 border-foreground"
    >
      {TABS.map((tab, i) => {
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
              "px-md py-sm font-mono text-micro uppercase tracking-widest transition-colors duration-[80ms]",
              i > 0 && "border-l-2 border-foreground",
              isActive
                ? "bg-foreground text-background"
                : "text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export function RunReportPanel({ data }: { data: ReportData }) {
  const [active, setActive] = useState<TabId>("overview");
  const activeTab = TABS.find((t) => t.id === active) ?? TABS[0];

  return (
    <div className="min-w-0 overflow-hidden">
      <TabBar active={active} onChange={setActive} />
      <RigorBanners data={data} />
      <div className="mt-xl border-2 border-node-border">
        <div className="flex items-center justify-between border-b-2 border-node-border bg-canvas px-5 py-3">
          <span className="font-mono text-xs uppercase tracking-[0.2em] text-neutral-faint">
            {activeTab.file}
          </span>
          <span className="font-mono text-xs tracking-[0.2em] text-neutral-faint opacity-50">
            {String(TABS.findIndex((t) => t.id === active) + 1).padStart(3, "0")}
          </span>
        </div>
        <div
          role="tabpanel"
          id={`panel-${active}`}
          aria-labelledby={`tab-${active}`}
          className="min-w-0 overflow-hidden p-xl"
          style={{ background: "var(--color-canvas)" }}
        >
          {active === "overview" && <Overview data={data} />}
          {active === "deltas" && <BehavioralDeltas data={data} />}
          {active === "attribution" && <Attribution data={data} />}
          {active === "timeline" && <Timeline data={data} />}
          {active === "summary" && <RunSummary data={data} />}
        </div>
      </div>
    </div>
  );
}

import { useState } from "react";
import { useReportData, shortRef } from "@/lib/payload";
import { Overview } from "@/sections/Overview";
import { BehavioralDeltas } from "@/sections/BehavioralDeltas";
import { Attribution } from "@/sections/Attribution";
import { Timeline } from "@/sections/Timeline";
import { RunSummary } from "@/sections/RunSummary";
import type { Verdict } from "@/types";

type Section = "overview" | "deltas" | "attribution" | "timeline" | "summary";

const NAV_ITEMS: { id: Section; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "deltas", label: "Behavioral Deltas" },
  { id: "attribution", label: "Causal Attribution" },
  { id: "timeline", label: "Trajectory Timeline" },
  { id: "summary", label: "Run Summary" },
];

function VerdictPill({ verdict }: { verdict: Verdict }) {
  const styles: Record<Verdict, string> = {
    fail: "bg-ember/15 text-ember border border-ember/30",
    warn: "bg-verdict-warn/15 text-verdict-warn border border-verdict-warn/30",
    pass: "bg-verdict-pass/15 text-verdict-pass border border-verdict-pass/30",
  };
  return (
    <span
      className={`inline-flex items-center rounded-sm px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest ${styles[verdict]}`}
    >
      {verdict}
    </span>
  );
}

export default function App() {
  const data = useReportData();
  const [section, setSection] = useState<Section>("overview");

  const verdict = data.graph.overall_verdict;
  const baseRef = shortRef(data.meta.baseline_ref);
  const candRef = shortRef(data.meta.candidate_ref);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-shell-dark text-ink-light">
      {/* ── Top bar ──────────────────────────────────────────────────── */}
      <header className="flex shrink-0 items-center justify-between border-b border-node-border px-xl py-md">
        <div className="flex items-center gap-md">
          {/* Wordmark */}
          <span className="font-display text-h2 font-bold tracking-tight text-ink-light">
            AgentDiff
          </span>
          <span className="hidden h-4 w-px bg-node-border sm:block" />
          {/* Refs */}
          <span className="hidden font-mono text-micro text-neutral-faint sm:inline">
            <span className="text-ink-light">{baseRef}</span>
            <span className="mx-xs">→</span>
            <span className="text-ink-light">{candRef}</span>
          </span>
        </div>
        <VerdictPill verdict={verdict} />
      </header>

      {/* ── Body: left rail + content ─────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left rail nav */}
        <nav className="flex w-48 shrink-0 flex-col gap-2xs border-r border-node-border px-sm py-lg">
          {NAV_ITEMS.map((item) => {
            const active = section === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setSection(item.id)}
                className={`rounded-sm px-md py-sm text-left text-small transition-colors duration-[80ms] ${
                  active
                    ? "bg-node-fill text-ink-light"
                    : "text-neutral-faint hover:bg-node-fill/50 hover:text-ink-light"
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Content column */}
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1240px] px-xl py-2xl">
            {section === "overview" && <Overview data={data} />}
            {section === "deltas" && <BehavioralDeltas data={data} />}
            {section === "attribution" && <Attribution data={data} />}
            {section === "timeline" && <Timeline data={data} />}
            {section === "summary" && <RunSummary data={data} />}
          </div>
        </main>
      </div>
    </div>
  );
}

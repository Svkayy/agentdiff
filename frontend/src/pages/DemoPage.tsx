import { Link } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  GitBranch,
  Network,
  ShieldCheck,
  Timer,
} from "lucide-react";
import { RunReportPanel } from "@/components/RunReportPanel";
import { toReportData } from "@/lib/payloadAdapter";
import { SAMPLE } from "@/sample";
import type { ReportData, Verdict } from "@/types";

const DEMO_DATA = toReportData(SAMPLE);

const VERDICT_LABEL: Record<Verdict, string> = {
  pass: "Stable",
  warn: "Notice",
  fail: "Change",
};

const VERDICT_STYLE: Record<Verdict, string> = {
  pass: "border-foreground text-foreground",
  warn: "border-[#ea580c] text-[#ea580c]",
  fail: "border-[#ea580c] bg-[#ea580c] text-background",
};

function formatRef(ref: string | null | undefined): string {
  if (!ref) return "unknown";
  return ref.length > 10 ? ref.slice(0, 10) : ref;
}

function formatTimestamp(value: string | null | undefined): string {
  const match = value?.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return "sample run";
  const [, year, month, day] = match;
  return new Date(`${year}-${month}-${day}T00:00:00Z`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

function countTimelineEvents(data: ReportData): number {
  return [...data.trajectories.baseline, ...data.trajectories.candidate].reduce(
    (total, trajectory) => total + trajectory.timeline.length,
    0,
  );
}

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return (
    <span
      className={`inline-flex border-2 px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest ${VERDICT_STYLE[verdict]}`}
    >
      {VERDICT_LABEL[verdict]}
    </span>
  );
}

function MetricTile({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof BarChart3;
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-h-[104px] flex-col justify-between border-2 border-foreground bg-background p-md">
      <div className="flex items-center justify-between gap-sm">
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          {label}
        </span>
        <Icon size={16} strokeWidth={1.75} aria-hidden="true" />
      </div>
      <span className="font-mono text-xl font-bold tabular-nums text-foreground">
        {value}
      </span>
    </div>
  );
}

function DemoProjectTable({ data }: { data: ReportData }) {
  const comparisons = data.comparison?.test_case_comparisons ?? [];

  return (
    <div className="border-2 border-foreground bg-background">
      <div className="flex items-center justify-between border-b-2 border-foreground px-md py-sm">
        <span className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-foreground">
          Demo Project
        </span>
        <span className="font-mono text-micro uppercase tracking-wider text-muted-foreground">
          Read-only
        </span>
      </div>
      <div className="grid min-w-0 gap-0 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="border-b-2 border-foreground p-lg lg:border-b-0 lg:border-r-2">
          <div className="mb-sm flex flex-wrap items-center gap-sm">
            <VerdictBadge verdict={data.graph.overall_verdict} />
            <span className="font-mono text-micro uppercase tracking-wider text-muted-foreground">
              CI Sample
            </span>
          </div>
          <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-foreground">
            Fact-checking agent
          </h2>
          <p className="mt-sm max-w-xl font-mono text-small leading-relaxed text-muted-foreground">
            A bundled AgentDiff payload with project metadata, run comparisons,
            graph changes, attribution, output checks, and captured timelines.
          </p>
          <div className="mt-lg flex flex-wrap gap-sm font-mono text-micro uppercase tracking-wider text-muted-foreground">
            <span>baseline {formatRef(data.meta.baseline_ref)}</span>
            <span>candidate {formatRef(data.meta.candidate_ref)}</span>
            <span>{formatTimestamp(data.meta.timestamp)}</span>
          </div>
        </div>
        <div className="min-w-0 overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b-2 border-foreground">
                <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                  Test case
                </th>
                <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                  Verdict
                </th>
                <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                  Signal
                </th>
              </tr>
            </thead>
            <tbody>
              {comparisons.map((comparison) => {
                const agentDelta = comparison.agent_invocation_deltas[0];
                const toolDelta = comparison.tool_usage_deltas[0];
                const signal =
                  agentDelta?.agent_name ??
                  toolDelta?.tool_name ??
                  `${Math.round((comparison.behavioral_overlap ?? 0) * 100)}% overlap`;
                return (
                  <tr key={comparison.test_case_id} className="border-b border-border last:border-b-0">
                    <td className="break-all px-md py-sm font-mono text-small text-foreground">
                      {comparison.test_case_id}
                    </td>
                    <td className="px-md py-sm">
                      <VerdictBadge verdict={comparison.overall_verdict} />
                    </td>
                    <td className="px-md py-sm font-mono text-micro text-muted-foreground">
                      {signal}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function DemoRunStrip({ data }: { data: ReportData }) {
  const comparisons = data.comparison?.test_case_comparisons ?? [];
  const changedCases = comparisons.filter((comparison) => comparison.overall_verdict !== "pass");
  const primaryCause = data.attribution?.attributions.find((entry) => entry.primary)?.primary;

  return (
    <div className="grid gap-md lg:grid-cols-3">
      <a
        href="#demo-report"
        className="group border-2 border-foreground bg-background p-lg transition-colors hover:border-[#ea580c]"
      >
        <div className="mb-sm flex items-center justify-between gap-md">
          <span className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-foreground">
            Demo Run
          </span>
          <ArrowRight
            size={16}
            strokeWidth={2}
            className="transition-transform group-hover:translate-x-1"
            aria-hidden="true"
          />
        </div>
        <div className="mb-sm">
          <VerdictBadge verdict={data.graph.overall_verdict} />
        </div>
        <p className="font-mono text-small leading-relaxed text-muted-foreground">
          {changedCases.length} changed cases across {comparisons.length} total checks,
          with the full report rendered below.
        </p>
      </a>
      <div className="border-2 border-foreground bg-background p-lg">
        <div className="mb-sm flex items-center justify-between gap-md">
          <span className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-foreground">
            Attribution
          </span>
          <GitBranch size={16} strokeWidth={1.75} aria-hidden="true" />
        </div>
        <p className="font-mono text-small leading-relaxed text-muted-foreground">
          Primary cause:{" "}
          <span className="text-foreground">
            {primaryCause?.target_path ?? "bundled sample"}
          </span>
        </p>
      </div>
      <div className="border-2 border-foreground bg-background p-lg">
        <div className="mb-sm flex items-center justify-between gap-md">
          <span className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-foreground">
            Mode
          </span>
          <ShieldCheck size={16} strokeWidth={1.75} aria-hidden="true" />
        </div>
        <p className="font-mono text-small leading-relaxed text-muted-foreground">
          Public, static, and read-only. No Clerk session, API server, Redis, or
          Postgres is required for this route.
        </p>
      </div>
    </div>
  );
}

export function DemoPage() {
  const comparisons = DEMO_DATA.comparison?.test_case_comparisons ?? [];
  const trajectories =
    DEMO_DATA.trajectories.baseline.length + DEMO_DATA.trajectories.candidate.length;
  const attributionCount = DEMO_DATA.attribution?.attributions.length ?? 0;

  return (
    <main className="w-full">
      <section className="mx-auto w-full max-w-[1240px] px-xl py-2xl">
        <div className="mb-2xl grid gap-xl lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
          <div>
            <div className="mb-sm font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
              public.demo
            </div>
            <h1 className="font-mono text-3xl font-bold uppercase tracking-tight text-foreground sm:text-4xl">
              AgentDiff demo workspace
            </h1>
            <p className="mt-md max-w-2xl font-mono text-small leading-relaxed text-muted-foreground">
              A static GitHub Pages preview backed by bundled sample data. Visitors
              can inspect demo projects, runs, graphs, attribution, timelines, and
              summaries without signing in.
            </p>
          </div>
          <div className="flex flex-wrap gap-sm lg:justify-end">
            <a
              href="#demo-report"
              className="inline-flex items-center gap-sm bg-foreground px-lg py-sm font-mono text-xs uppercase tracking-wider text-background transition-opacity hover:opacity-85"
            >
              <BarChart3 size={16} strokeWidth={2} aria-hidden="true" />
              View Report
            </a>
            <Link
              to="/projects"
              className="inline-flex items-center gap-sm border-2 border-foreground bg-background px-lg py-sm font-mono text-xs uppercase tracking-wider text-foreground transition-colors hover:bg-foreground hover:text-background"
            >
              <ArrowRight size={16} strokeWidth={2} aria-hidden="true" />
              Open Dashboard
            </Link>
          </div>
        </div>

        <div className="mb-xl grid gap-md sm:grid-cols-2 lg:grid-cols-4">
          <MetricTile icon={Network} label="Graph nodes" value={String(DEMO_DATA.graph.nodes.length)} />
          <MetricTile icon={BarChart3} label="Test cases" value={String(comparisons.length)} />
          <MetricTile icon={GitBranch} label="Attributions" value={String(attributionCount)} />
          <MetricTile icon={Timer} label="Timeline events" value={String(countTimelineEvents(DEMO_DATA))} />
        </div>

        <div className="space-y-xl">
          <DemoProjectTable data={DEMO_DATA} />
          <DemoRunStrip data={DEMO_DATA} />
        </div>
      </section>

      <section id="demo-report" className="mx-auto w-full max-w-[1240px] px-xl pb-2xl">
        <div className="mb-lg flex flex-wrap items-end justify-between gap-md border-t-2 border-foreground pt-xl">
          <div>
            <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
              report.payload
            </div>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-foreground">
              Sample run report
            </h2>
          </div>
          <span className="font-mono text-micro uppercase tracking-wider text-muted-foreground">
            {trajectories} trajectories
          </span>
        </div>
        <RunReportPanel data={DEMO_DATA} />
      </section>
    </main>
  );
}

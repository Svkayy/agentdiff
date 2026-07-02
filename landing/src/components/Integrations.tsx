import { CardHoverEffect, type HoverCard } from "./aceternity/CardHoverEffect";

function ActionSnippet() {
  return (
    <pre className="overflow-x-auto rounded-md border border-nodeborder bg-canvas p-4 font-mono text-[11px] leading-relaxed text-canvastext">
      <span className="text-faint">{"- uses: "}</span>agentdiff/gate-action@v1
      {"\n"}
      <span className="text-faint">{"  with:"}</span>
      {"\n"}
      <span className="text-faint">{"    baseline: "}</span>origin/main
      {"\n"}
      <span className="text-faint">{"    tier: "}</span>hermetic
    </pre>
  );
}

const ITEMS: HoverCard[] = [
  {
    id: "github-actions",
    title: "GitHub Actions",
    description:
      "A composite action runs the gate on every PR and annotates the diff. FAIL exits 1 and blocks the merge.",
    body: <ActionSnippet />,
  },
  {
    id: "slack",
    title: "Slack",
    description:
      "Failed gates post the brief to your channel: impact, likely cause, and one-click links to the report, PR, and CI run.",
    body: (
      <div className="rounded-md border border-nodeborder bg-canvas p-4 font-mono text-[11px] leading-relaxed">
        <span style={{ color: "#FF4D2E" }}>🔴 Fact Checker invocation changed</span>
        <span className="mt-1 block text-faint">#agent-ci · acme/support-bot · PR #482</span>
      </div>
    ),
  },
  {
    id: "webhook",
    title: "Webhook → Linear, Jira, PagerDuty",
    description:
      "A generic JSON webhook carries the full verdict payload, so you can open a Linear issue, a Jira ticket, or a PagerDuty incident from any regression.",
    body: (
      <pre className="overflow-x-auto rounded-md border border-nodeborder bg-canvas p-4 font-mono text-[11px] leading-relaxed text-canvastext">
        {'{ "verdict": "FAIL",\n  "delta": "fact_checker -100%",\n  "cause": "agents/fact_checker.py" }'}
      </pre>
    ),
  },
];

export function Integrations() {
  return (
    <section id="integrations" aria-labelledby="integrations-heading" className="border-b border-hairline">
      <div className="mx-auto max-w-content px-5 py-20">
        <div className="max-w-2xl">
          <p className="font-mono text-[12px] uppercase tracking-[0.16em] text-muted">
            Integrations
          </p>
          <h2
            id="integrations-heading"
            className="mt-3 font-display text-3xl font-bold tracking-tight text-ink"
          >
            Drops into the pipeline you already have.
          </h2>
        </div>
        <CardHoverEffect items={ITEMS} className="mt-10" />
      </div>
    </section>
  );
}

import { Timeline, type TimelineEntry } from "./aceternity/Timeline";

function Cmd({ children }: { children: string }) {
  return (
    <code className="mt-3 block w-fit max-w-full overflow-x-auto rounded-sm border border-hairline bg-card px-3 py-2 font-mono text-[13px] text-ink">
      {children}
    </code>
  );
}

const ENTRIES: TimelineEntry[] = [
  {
    step: "agentdiff init",
    title: "Point it at your agent",
    content: (
      <>
        <p>
          One command scans the project, infers agents, tools, and entry points, and
          scaffolds <span className="font-mono text-[13px]">.agentdiff/</span>. No
          framework required — capture happens at the HTTP layer.
        </p>
        <Cmd>agentdiff init</Cmd>
      </>
    ),
  },
  {
    step: "record",
    title: "Record a cassette",
    content: (
      <>
        <p>
          Run your agent once while AgentDiff records every LLM and tool call. The
          cassette becomes the deterministic baseline the hermetic tier replays for
          free on every PR.
        </p>
        <Cmd>agentdiff ci run --cassette-mode record --baseline origin/main</Cmd>
      </>
    ),
  },
  {
    step: "ci gate",
    title: "Gate the pull request",
    content: (
      <>
        <p>
          In CI, AgentDiff replays baseline and candidate, diffs the behavior, and
          exits non-zero when a sub-agent stops firing or tool usage shifts
          significantly. Output evals can keep saying PASS — the gate checks behavior.
        </p>
        <Cmd>agentdiff ci run --tier hermetic --baseline origin/main</Cmd>
      </>
    ),
  },
  {
    step: "slack brief",
    title: "The team gets the brief",
    content: (
      <p>
        A failed gate posts a Slack brief: what changed, how much, the likely cause
        file and hunk, and links to the report, the PR, and the CI run. No dashboard
        spelunking to find out what broke.
      </p>
    ),
  },
  {
    step: "postmortem",
    title: "Attribute and fix",
    content: (
      <p>
        The full report pins the regression to the exact commit and diff hunk, with
        the alternatives the rule engine considered. Revert the line or accept the new
        behavior as the baseline — either way, it&rsquo;s a decision, not a surprise.
      </p>
    ),
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" aria-labelledby="how-heading" className="border-b border-hairline">
      <div className="mx-auto max-w-content px-5 py-20">
        <div className="max-w-2xl">
          <p className="font-mono text-[12px] uppercase tracking-[0.16em] text-muted">
            How it works
          </p>
          <h2
            id="how-heading"
            className="mt-3 font-display text-3xl font-bold tracking-tight text-ink"
          >
            From install to postmortem in five steps.
          </h2>
        </div>
        <div className="mt-12 max-w-3xl">
          <Timeline entries={ENTRIES} />
        </div>
      </div>
    </section>
  );
}

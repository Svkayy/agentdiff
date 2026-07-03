import { BentoGrid, BentoGridItem } from "./aceternity/BentoGrid";

const EMBER = "#FF4D2E";

function StatHeader() {
  return (
    <div className="rounded-md border border-nodeborder bg-canvas p-4 font-mono text-[11px] leading-relaxed">
      <div className="flex justify-between text-canvastext">
        <span>fact_checker.invocation_rate</span>
        <span className="tabular" style={{ color: EMBER }}>
          100% → 0%
        </span>
      </div>
      <div className="mt-1 flex justify-between text-faint">
        <span>two-proportion z-test</span>
        <span className="tabular">p&lt;0.001</span>
      </div>
      <div className="mt-1 flex justify-between text-faint">
        <span>tool_calls / run</span>
        <span className="tabular">Mann–Whitney U</span>
      </div>
    </div>
  );
}

function HunkHeader() {
  return (
    <div className="rounded-md border border-nodeborder bg-canvas p-4 font-mono text-[11px] leading-relaxed">
      <div className="text-faint">@@ agents/fact_checker.py @@</div>
      <div className="text-canvastext">
        <span className="text-pass">+</span>{" "}
        <span>return None&nbsp;&nbsp;# TODO: re-enable</span>
      </div>
      <div className="mt-1 text-faint">
        rule: call_removed · confidence 0.90
      </div>
    </div>
  );
}

function ExitCodeHeader() {
  return (
    <div className="rounded-md border border-nodeborder bg-canvas p-4 font-mono text-[11px] leading-relaxed">
      <div className="flex justify-between">
        <span className="text-pass">PASS</span>
        <span className="tabular text-faint">exit 0</span>
      </div>
      <div className="mt-1 flex justify-between">
        <span className="text-warn">WARN</span>
        <span className="tabular text-faint">exit 0 · annotates PR</span>
      </div>
      <div className="mt-1 flex justify-between">
        <span style={{ color: EMBER }}>FAIL</span>
        <span className="tabular text-faint">exit 1 · blocks merge</span>
      </div>
    </div>
  );
}

const FEATURES = [
  {
    kicker: "Diff engine",
    title: "Behavioral diffs, with real statistics",
    description:
      "Agent invocation rates, tool usage, and handoffs compared with two-proportion z-tests and Mann–Whitney U — significance, not vibes.",
    header: <StatHeader />,
    className: "md:col-span-2",
  },
  {
    kicker: "Attribution",
    title: "Named to the exact hunk",
    description:
      "A deterministic rule engine maps every non-passing delta to the changed file and unified-diff hunk that caused it. The LLM only writes the explanation, never the verdict.",
    header: <HunkHeader />,
  },
  {
    kicker: "Hermetic tier",
    title: "Cassette replay: $0, deterministic",
    description:
      "Record a cassette of real LLM traffic once, replay it on every PR. No API keys in CI, no flaky samples, no per-run token bill.",
  },
  {
    kicker: "Live tier",
    title: "Statistical sampling when it matters",
    description:
      "For release gates, run live samples against both refs and let the statistics decide — with a configurable failure budget for stochastic agents.",
  },
  {
    kicker: "CI gate",
    title: "Exit codes CI understands",
    description:
      "PASS, WARN, and FAIL map to plain exit codes and PR annotations, so the gate drops into any pipeline without a plugin.",
    header: <ExitCodeHeader />,
  },
  {
    kicker: "Delivery",
    title: "Degrade, never swallow",
    description:
      "If Slack is down or a webhook fails, the brief lands in the CI log and the report artifact instead. A delivery failure never hides a regression.",
    className: "md:col-span-2",
  },
];

export function Features() {
  return (
    <section aria-labelledby="features-heading" className="border-b border-hairline">
      <div className="mx-auto max-w-content px-5 py-20">
        <div className="max-w-2xl">
          <p className="font-mono text-[12px] uppercase tracking-[0.16em] text-muted">
            What&rsquo;s in the box
          </p>
          <h2
            id="features-heading"
            className="mt-3 font-display text-3xl font-bold tracking-tight text-ink"
          >
            A regression surface that matches how agents actually break.
          </h2>
        </div>
        <BentoGrid className="mt-10">
          {FEATURES.map((f, i) => (
            <BentoGridItem
              key={f.title}
              index={i}
              kicker={f.kicker}
              title={f.title}
              description={f.description}
              header={f.header}
              className={f.className}
            />
          ))}
        </BentoGrid>
      </div>
    </section>
  );
}

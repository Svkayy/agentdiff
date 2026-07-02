import { motion } from "framer-motion";
import { useSkipEntrance } from "@/lib/utils";

const EMBER = "#FF4D2E";

function SlackButton({ label }: { label: string }) {
  return (
    <span className="inline-flex cursor-default items-center rounded-sm border border-nodeborder bg-node px-3 py-1.5 font-body text-[13px] font-medium text-canvastext">
      {label}
    </span>
  );
}

/**
 * A realistic mock of the Slack brief AgentDiff posts when the CI gate fails.
 * Dark panel, ember left color bar — the ember here IS the regression signal.
 */
export function SlackBrief() {
  const skip = useSkipEntrance();
  return (
    <section aria-labelledby="slack-brief-heading" className="border-b border-hairline">
      <div className="mx-auto max-w-content px-5 py-20">
        <div className="max-w-2xl">
          <p className="font-mono text-[12px] uppercase tracking-[0.16em] text-muted">
            The Slack brief
          </p>
          <h2
            id="slack-brief-heading"
            className="mt-3 font-display text-3xl font-bold tracking-tight text-ink"
          >
            Your team finds out in Slack, not in production.
          </h2>
          <p className="mt-3 text-[15px] leading-relaxed text-muted">
            When the gate fails, AgentDiff posts a brief with the behavioral delta, the
            likely cause, and links to the report, the PR, and the CI run.
          </p>
        </div>

        <motion.div
          initial={skip ? false : { y: 14 }}
          whileInView={{ y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.32, ease: "easeOut" }}
          className="mx-auto mt-10 max-w-2xl overflow-hidden rounded-lg border border-hairline bg-canvas shadow-[0_24px_60px_rgba(21,24,29,0.18)]"
        >
          <div className="flex items-center gap-2 border-b border-nodeborder px-5 py-3">
            <span className="h-2.5 w-2.5 rounded-full bg-nodeborder" aria-hidden="true" />
            <span className="h-2.5 w-2.5 rounded-full bg-nodeborder" aria-hidden="true" />
            <span className="h-2.5 w-2.5 rounded-full bg-nodeborder" aria-hidden="true" />
            <span className="ml-3 font-mono text-[11px] text-faint">#agent-ci</span>
          </div>

          <div className="p-5">
            <div className="flex gap-3">
              <div
                aria-hidden="true"
                className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-node font-mono text-sm text-canvastext"
              >
                Δ
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="font-body text-[15px] font-bold text-canvastext">
                    AgentDiff
                  </span>
                  <span className="rounded-sm bg-node px-1.5 py-0.5 font-mono text-[10px] uppercase text-faint">
                    App
                  </span>
                  <span className="font-mono text-[11px] tabular text-faint">14:02</span>
                </div>

                {/* Ember left color bar — the Slack attachment accent. */}
                <div className="mt-2 border-l-[3px] pl-4" style={{ borderColor: EMBER }}>
                  <p className="font-body text-[15px] font-bold leading-snug text-canvastext">
                    🔴 AgentDiff: Fact Checker invocation changed
                  </p>
                  <p className="mt-1.5 font-mono text-[12px] leading-relaxed text-faint">
                    acme/support-bot · PR #482 · origin/main → working · hermetic tier
                  </p>
                  <p className="mt-3 font-body text-[14px] leading-relaxed text-canvastext">
                    <strong className="font-semibold">Impact:</strong> Fact Checker fired
                    100% on baseline and 0% on candidate (
                    <span className="tabular" style={{ color: EMBER }}>
                      −100%
                    </span>
                    ).
                  </p>
                  <p className="mt-1.5 font-body text-[14px] leading-relaxed text-canvastext">
                    <strong className="font-semibold">Likely cause:</strong>{" "}
                    <span className="font-mono text-[13px]">agents/fact_checker.py</span>{" "}
                    — <span className="font-mono text-[13px]">call_removed</span>
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <SlackButton label="Open report" />
                    <SlackButton label="View PR" />
                    <SlackButton label="CI run" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

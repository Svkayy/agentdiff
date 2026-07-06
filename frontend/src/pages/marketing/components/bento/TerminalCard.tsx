import { useEffect, useState } from "react";

// A truthful-flavored `agentdiff compare` run: sample the baseline/candidate
// trajectories, compute behavioral deltas, BH-adjust the p-values, attribute
// the regression to a hunk, and print the verdict.
const LOG_LINES = [
  "$ agentdiff compare --baseline main --candidate HEAD",
  "> loading baseline run: 40 trajectories",
  "> loading candidate run: 40 trajectories",
  "> sampling fact_checker invocation rate...",
  "> baseline 0.98  candidate 0.10  delta -0.88",
  "> two-proportion z-test  p=0.0003",
  "> benjamini-hochberg adjust  p_adj=0.0011  (a=0.05)",
  "> significant: TRUE  low_power: FALSE",
  "> attributing regression...",
  "> hunk: agents/router.py:42  -fact_checker.run(claim)",
  "> tool_usage delta: search 1.4 -> 0.0",
  "> verdict: FAIL",
  "> ---------- COMPARE COMPLETE ----------",
];

/**
 * Bento terminal card — ported from the template's `terminal-card.tsx`,
 * cycling AgentDiff `compare` log lines (sampling → deltas → BH-adjusted p →
 * attribution hunk → FAIL verdict).
 */
export function TerminalCard() {
  const [lines, setLines] = useState<string[]>([]);
  const [currentLine, setCurrentLine] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentLine((prev) => {
        const next = prev + 1;
        if (next >= LOG_LINES.length) {
          setLines([]);
          return 0;
        }
        setLines((l) => [...l.slice(-8), LOG_LINES[next]]);
        return next;
      });
    }, 700);

    setLines([LOG_LINES[0]]);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 border-b-2 border-foreground px-4 py-2">
        <span className="h-2 w-2 bg-[#ea580c]" />
        <span className="h-2 w-2 bg-foreground" />
        <span className="h-2 w-2 border border-foreground" />
        <span className="ml-auto text-[11px] tracking-widest text-muted-foreground uppercase">
          agentdiff-compare.sh
        </span>
      </div>
      <div className="flex-1 bg-foreground p-4 overflow-hidden">
        <div className="flex flex-col gap-1">
          {lines.map((line, i) => {
            const isVerdict = line.includes("verdict: FAIL");
            return (
              <span
                key={`${currentLine}-${i}`}
                className={`text-sm font-mono block leading-relaxed ${isVerdict ? "text-[#ea580c] font-bold" : "text-background"}`}
                style={{ opacity: i === lines.length - 1 ? 1 : 0.7 }}
              >
                {line}
              </span>
            );
          })}
          <span className="text-sm text-[#ea580c] font-mono animate-blink">{"_"}</span>
        </div>
      </div>
    </div>
  );
}

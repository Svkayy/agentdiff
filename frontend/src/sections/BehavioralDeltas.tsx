import { useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { verdictColor } from "@/lib/payload";
import type {
  AgentInvocationDelta,
  ReportData,
  RunMetricDelta,
  TestCaseComparison,
  ToolUsageDelta,
  Verdict,
} from "@/types";

// ── Verdict badge ─────────────────────────────────────────────────────────────
// Verdict mapping (DESIGN.md, locked): pass = neutral cream chip;
// warn = orange OUTLINE; fail = solid orange.
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

// ── Format p-value for display ────────────────────────────────────────────────
function fmtP(p: number | null, significant: boolean): string {
  if (p === null) return "—";
  const raw = p < 0.001 ? "<0.001" : p.toFixed(3);
  return significant ? `${raw}*` : raw;
}

// ── Format rate for agents ────────────────────────────────────────────────────
function fmtRate(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

// ── Format avg for tools ──────────────────────────────────────────────────────
function fmtAvg(avg: number): string {
  return avg.toFixed(2);
}

// ── Delta display ─────────────────────────────────────────────────────────────
function DeltaCell({ delta, isEmber }: { delta: number; isEmber: boolean }) {
  const sign = delta > 0 ? "+" : "";
  const cls = isEmber ? "text-[#ea580c] font-bold" : delta < 0 ? "text-[#ea580c]" : "text-ink-light";
  return (
    <span className={`font-mono tabular-nums ${cls}`}>
      {sign}
      {delta.toFixed(2)}
    </span>
  );
}

// ── Unified row type ──────────────────────────────────────────────────────────
type UnifiedRow =
  | { kind: "agent"; data: AgentInvocationDelta }
  | { kind: "tool"; data: ToolUsageDelta };

function buildRows(tc: TestCaseComparison): UnifiedRow[] {
  const agents: UnifiedRow[] = tc.agent_invocation_deltas.map((d) => ({
    kind: "agent",
    data: d,
  }));
  const tools: UnifiedRow[] = tc.tool_usage_deltas.map((d) => ({
    kind: "tool",
    data: d,
  }));
  return [...agents, ...tools];
}

// ── Delta table for one test case ─────────────────────────────────────────────
function DeltaTable({ tc }: { tc: TestCaseComparison }) {
  const rows = buildRows(tc);
  if (rows.length === 0) {
    return (
      <p className="py-md text-small text-neutral-faint">No delta data for this test case.</p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow className="border-node-border">
          <TableHead className="text-micro uppercase tracking-widest text-neutral-faint font-mono">
            Name
          </TableHead>
          <TableHead className="text-micro uppercase tracking-widest text-neutral-faint font-mono">
            Kind
          </TableHead>
          <TableHead className="text-right text-micro uppercase tracking-widest text-neutral-faint font-mono">
            Baseline
          </TableHead>
          <TableHead className="text-right text-micro uppercase tracking-widest text-neutral-faint font-mono">
            Candidate
          </TableHead>
          <TableHead className="text-right text-micro uppercase tracking-widest text-neutral-faint font-mono">
            Δ
          </TableHead>
          <TableHead className="text-right text-micro uppercase tracking-widest text-neutral-faint font-mono">
            p-value
          </TableHead>
          <TableHead className="text-micro uppercase tracking-widest text-neutral-faint font-mono">
            Verdict
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, idx) => {
          if (row.kind === "agent") {
            const d = row.data;
            const isStopped =
              d.verdict !== "pass" && d.candidate_rate === 0;
            return (
              <TableRow
                key={`agent-${d.agent_name}-${idx}`}
                className={`border-node-border transition-colors ${
                  isStopped ? "bg-[#ea580c]/10" : "hover:bg-node-fill/50"
                }`}
              >
                <TableCell className="font-mono text-small text-ink-light">
                  <span className={isStopped ? "text-[#ea580c] font-bold" : ""}>{d.agent_name}</span>
                  {isStopped && (
                    <span className="ml-sm border-2 border-[#ea580c] bg-[#ea580c]/15 px-xs py-2xs font-mono text-micro text-[#ea580c]">
                      STOPPED
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  <span className="border-2 border-node-border bg-node-fill px-xs py-2xs font-mono text-micro text-neutral-faint">
                    agent
                  </span>
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums text-small text-ink-light">
                  {fmtRate(d.baseline_rate)}
                </TableCell>
                <TableCell
                  className={`text-right font-mono tabular-nums text-small ${
                    isStopped ? "text-[#ea580c] font-bold" : "text-ink-light"
                  }`}
                >
                  {fmtRate(d.candidate_rate)}
                </TableCell>
                <TableCell className="text-right">
                  <DeltaCell delta={d.delta} isEmber={isStopped} />
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums text-small text-neutral-faint">
                  {fmtP(d.p_value, d.significant)}
                </TableCell>
                <TableCell>
                  <VerdictBadge verdict={d.verdict} />
                </TableCell>
              </TableRow>
            );
          } else {
            const d = row.data;
            const isStopped = d.verdict !== "pass" && d.candidate_avg === 0;
            return (
              <TableRow
                key={`tool-${d.tool_name}-${idx}`}
                className={`border-node-border transition-colors ${
                  isStopped ? "bg-[#ea580c]/10" : "hover:bg-node-fill/50"
                }`}
              >
                <TableCell className="font-mono text-small text-ink-light">
                  <span className={isStopped ? "text-[#ea580c] font-bold" : ""}>{d.tool_name}</span>
                </TableCell>
                <TableCell>
                  <span className="border-2 border-node-border bg-node-fill px-xs py-2xs font-mono text-micro text-neutral-faint">
                    tool
                  </span>
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums text-small text-ink-light">
                  {fmtAvg(d.baseline_avg)}
                </TableCell>
                <TableCell
                  className={`text-right font-mono tabular-nums text-small ${
                    isStopped ? "text-[#ea580c] font-bold" : "text-ink-light"
                  }`}
                >
                  {fmtAvg(d.candidate_avg)}
                </TableCell>
                <TableCell className="text-right">
                  <DeltaCell delta={d.delta} isEmber={isStopped} />
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums text-small text-neutral-faint">
                  {fmtP(d.p_value, d.significant)}
                </TableCell>
                <TableCell>
                  <VerdictBadge verdict={d.verdict} />
                </TableCell>
              </TableRow>
            );
          }
        })}
      </TableBody>
    </Table>
  );
}

// ── Run metric labels/formatting ──────────────────────────────────────────────
const METRIC_LABELS: Record<RunMetricDelta["metric"], string> = {
  latency_ms: "Latency",
  total_tokens: "Total Tokens",
  error_rate: "Error Rate",
};

function fmtMetricValue(metric: RunMetricDelta["metric"], value: number): string {
  if (metric === "latency_ms") return `${Math.round(value)}ms`;
  if (metric === "error_rate") return `${(value * 100).toFixed(1)}%`;
  return Math.round(value).toLocaleString();
}

// ── Run-level metric deltas (latency/tokens/error-rate — Task 7/8) ───────────
function RunMetricsTable({ metrics }: { metrics: RunMetricDelta[] }) {
  if (metrics.length === 0) return null;

  return (
    <div className="border-2 border-node-border bg-node-fill/30">
      <div className="border-b border-node-border px-md py-sm font-mono text-micro uppercase tracking-widest text-neutral-faint">
        Runtime Metrics
      </div>
      <Table>
        <TableHeader>
          <TableRow className="border-node-border">
            <TableHead className="text-micro uppercase tracking-widest text-neutral-faint font-mono">
              Metric
            </TableHead>
            <TableHead className="text-right text-micro uppercase tracking-widest text-neutral-faint font-mono">
              Baseline
            </TableHead>
            <TableHead className="text-right text-micro uppercase tracking-widest text-neutral-faint font-mono">
              Candidate
            </TableHead>
            <TableHead className="text-right text-micro uppercase tracking-widest text-neutral-faint font-mono">
              Δ
            </TableHead>
            <TableHead className="text-right text-micro uppercase tracking-widest text-neutral-faint font-mono">
              p-value
            </TableHead>
            <TableHead className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
              Verdict
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {metrics.map((m) => {
            const isEmber = m.verdict === "fail";
            return (
              <TableRow key={m.metric} className="border-node-border transition-colors hover:bg-node-fill/50">
                <TableCell className="font-mono text-small text-ink-light">
                  {METRIC_LABELS[m.metric]}
                  {m.low_power && (
                    <span
                      className="ml-sm border-2 border-[#ea580c] px-xs py-2xs font-mono text-micro text-[#ea580c]"
                      title="Sample size below the configured minimum — treat this delta cautiously"
                    >
                      low power
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums text-small text-ink-light">
                  {fmtMetricValue(m.metric, m.baseline_mean)}
                </TableCell>
                <TableCell
                  className={`text-right font-mono tabular-nums text-small ${
                    isEmber ? "text-[#ea580c] font-bold" : "text-ink-light"
                  }`}
                >
                  {fmtMetricValue(m.metric, m.candidate_mean)}
                </TableCell>
                <TableCell className="text-right">
                  <DeltaCell delta={m.delta} isEmber={isEmber} />
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums text-small text-neutral-faint">
                  {fmtP(m.p_value, m.adjusted_p_value !== null && m.adjusted_p_value < 0.05)}
                </TableCell>
                <TableCell>
                  <VerdictBadge verdict={m.verdict} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// ── Case selector tabs ────────────────────────────────────────────────────────
function CaseTabs({
  cases,
  active,
  onChange,
}: {
  cases: TestCaseComparison[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="flex gap-xs border-b border-node-border">
      {cases.map((tc) => {
        const isActive = tc.test_case_id === active;
        const verdictAccent = verdictColor(tc.overall_verdict);
        return (
          <button
            key={tc.test_case_id}
            onClick={() => onChange(tc.test_case_id)}
            className={`flex items-center gap-xs px-md py-sm font-mono text-small transition-colors duration-[80ms] ${
              isActive
                ? "border-b-2 border-ink-light bg-node-fill text-ink-light -mb-px"
                : "text-neutral-faint hover:text-ink-light"
            }`}
          >
            {/* Verdict dot (locked mapping): fail = solid orange; warn = orange
                outline; pass = neutral cream. */}
            <span
              className={`h-2 w-2 ${
                verdictAccent === "ember"
                  ? "bg-[#ea580c]"
                  : verdictAccent === "verdict-warn"
                    ? "border-2 border-[#ea580c] bg-transparent"
                    : "bg-ink-light"
              }`}
            />
            {tc.test_case_id}
          </button>
        );
      })}
    </div>
  );
}

// ── BehavioralDeltas section ──────────────────────────────────────────────────
export function BehavioralDeltas({ data }: { data: ReportData }) {
  const tcs = data.comparison?.test_case_comparisons ?? [];
  const [activeId, setActiveId] = useState<string>(tcs[0]?.test_case_id ?? "");

  const activeCase = tcs.find((tc) => tc.test_case_id === activeId) ?? tcs[0];

  if (tcs.length === 0) {
    return (
      <div className="space-y-lg">
        <h1 className="font-display text-h1 font-bold text-ink-light">Behavioral Deltas</h1>
        <p className="text-small text-neutral-faint">No comparison data in this run.</p>
      </div>
    );
  }

  return (
    <div className="space-y-xl">
      <div>
        <h1 className="font-display text-h1 font-bold text-ink-light">Behavioral Deltas</h1>
        <p className="mt-xs text-small text-neutral-faint">
          Per-test-case breakdown of agent invocation rates and tool usage — asterisk (*) denotes
          statistical significance.
        </p>
      </div>

      {/* Case tabs */}
      <div>
        <CaseTabs cases={tcs} active={activeId} onChange={setActiveId} />

        {activeCase && (
          <div className="mt-md space-y-md">
            {/* Case header */}
            <div className="flex items-center gap-md">
              <code className="font-mono text-small text-ink-light">{activeCase.test_case_id}</code>
              <VerdictBadge verdict={activeCase.overall_verdict} />
              {activeCase.behavioral_overlap !== null && (
                <span className="font-mono text-micro text-neutral-faint">
                  Behavioral overlap:{" "}
                  <span className="text-ink-light">
                    {Math.round(activeCase.behavioral_overlap * 100)}%
                  </span>
                </span>
              )}
            </div>

            {/* Delta table */}
            <div className="border-2 border-node-border bg-node-fill/30">
              <DeltaTable tc={activeCase} />
            </div>

            {/* Runtime metric deltas (latency/tokens/error-rate — Task 7/8) */}
            <RunMetricsTable metrics={activeCase.run_metrics ?? []} />
          </div>
        )}
      </div>

      {/* Footer note on stopped rows */}
      <p className="text-micro text-neutral-faint">
        Rows with ember background: agent stopped firing in candidate (candidate rate = 0). Runtime
        metrics tagged &quot;low power&quot; have a per-side sample size below the configured minimum.
      </p>
    </div>
  );
}

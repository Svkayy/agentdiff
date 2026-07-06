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
import { shortRef } from "@/lib/payload";
import type { OutputEval, ReportData, Verdict } from "@/types";

// ── Verdict badge ─────────────────────────────────────────────────────────────
// Verdict mapping (DESIGN.md, locked): pass = neutral cream; warn = orange
// OUTLINE; fail = solid orange.
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

// Normalize verdict string (engine emits lowercase)
function asVerdict(v: string): Verdict {
  const lower = v.toLowerCase();
  if (lower === "pass" || lower === "warn" || lower === "fail") return lower as Verdict;
  return "fail";
}

// ── Format nullable number ────────────────────────────────────────────────────
function fmt(n: number | null, decimals = 2): string {
  if (n === null || n === undefined) return "—";
  return n.toFixed(decimals);
}

function fmtPct(n: number | null): string {
  if (n === null || n === undefined) return "—";
  return `${Math.round(n * 100)}%`;
}

// ── Copy button ───────────────────────────────────────────────────────────────
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore clipboard errors
    }
  };
  return (
    <button
      onClick={handleCopy}
      className="border-2 border-node-border bg-node-fill px-sm py-2xs font-mono text-micro text-neutral-faint transition-colors hover:bg-node-fill/50 hover:text-ink-light"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

// ── Run quality table ─────────────────────────────────────────────────────────
function RunQualityTable({ data }: { data: ReportData }) {
  const rq = data.runQuality;

  const rows = [
    {
      side: "Baseline",
      trajectories: rq.baseline_trajectories,
      failed: rq.baseline_failed,
      budget: rq.max_failure_rate,
    },
    {
      side: "Candidate",
      trajectories: rq.candidate_trajectories,
      failed: rq.candidate_failed,
      budget: rq.max_failure_rate,
    },
  ];

  return (
    <Table>
      <TableHeader>
        <TableRow className="border-node-border">
          <TableHead className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Side
          </TableHead>
          <TableHead className="text-right font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Trajectories
          </TableHead>
          <TableHead className="text-right font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Failed
          </TableHead>
          <TableHead className="text-right font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Failure Budget
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.side} className="border-node-border hover:bg-node-fill/50">
            <TableCell className="font-mono text-small text-ink-light">{row.side}</TableCell>
            <TableCell className="text-right font-mono tabular-nums text-small text-ink-light">
              {row.trajectories ?? "—"}
            </TableCell>
            <TableCell className="text-right font-mono tabular-nums text-small text-ink-light">
              {row.failed ?? "—"}
            </TableCell>
            <TableCell className="text-right font-mono tabular-nums text-small text-ink-light">
              {fmtPct(row.budget)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// ── Thresholds card ───────────────────────────────────────────────────────────
function ThresholdsCard({ data }: { data: ReportData }) {
  const t = data.runQuality.thresholds;
  if (!t) return null;

  const items = [
    { label: "Agent Invocation — Warn", value: fmtPct(t.agent_invocation_rate_warn) },
    { label: "Agent Invocation — Fail", value: fmtPct(t.agent_invocation_rate_fail) },
    { label: "Tool Usage Avg — Warn", value: fmt(t.tool_usage_avg_warn) },
    { label: "Tool Usage Avg — Fail", value: fmt(t.tool_usage_avg_fail) },
  ];

  return (
    <div className="border-2 border-node-border bg-node-fill p-md">
      <div className="mb-sm font-mono text-micro uppercase tracking-widest text-neutral-faint">
        Thresholds
      </div>
      <div className="grid grid-cols-2 gap-sm sm:grid-cols-4">
        {items.map((item) => (
          <div key={item.label} className="space-y-2xs">
            <div className="font-mono text-micro text-neutral-faint">{item.label}</div>
            <div className="font-mono text-small tabular-nums font-bold text-ink-light">
              {item.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Output eval table ─────────────────────────────────────────────────────────
function OutputEvalTable({ evals }: { evals: OutputEval[] }) {
  if (evals.length === 0) {
    return (
      <p className="py-md text-small text-neutral-faint">No output eval data in this run.</p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow className="border-node-border">
          <TableHead className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Test Case
          </TableHead>
          <TableHead className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Kind
          </TableHead>
          <TableHead className="text-right font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Semantic
          </TableHead>
          <TableHead className="text-right font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Structural
          </TableHead>
          <TableHead className="text-right font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Length
          </TableHead>
          <TableHead className="text-right font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Judge
          </TableHead>
          <TableHead className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Verdict
          </TableHead>
          <TableHead className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Notes
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {evals.map((e) => (
          <TableRow key={e.test_case_id} className="border-node-border hover:bg-node-fill/50">
            <TableCell className="font-mono text-small text-ink-light">
              {e.test_case_id}
            </TableCell>
            <TableCell className="font-mono text-small text-neutral-faint">{e.output_kind}</TableCell>
            <TableCell className="text-right font-mono tabular-nums text-small text-ink-light">
              {fmt(e.semantic_similarity)}
            </TableCell>
            <TableCell className="text-right font-mono tabular-nums text-small text-ink-light">
              {fmt(e.structural_similarity)}
            </TableCell>
            <TableCell className="text-right font-mono tabular-nums text-small text-ink-light">
              {fmt(e.length_ratio)}
            </TableCell>
            <TableCell className="text-right font-mono tabular-nums text-small text-ink-light">
              {fmt(e.judge_score, 1)}
            </TableCell>
            <TableCell>
              <VerdictBadge verdict={asVerdict(e.verdict)} />
            </TableCell>
            <TableCell className="max-w-[200px] text-small text-neutral-faint">
              {e.notes.length > 0 ? e.notes.join("; ") : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// ── Reproduction block ────────────────────────────────────────────────────────
function ReproBlock({ data }: { data: ReportData }) {
  const baseRef = shortRef(data.meta.baseline_ref);
  const samples =
    data.meta.samples_per_case !== null && data.meta.samples_per_case !== undefined
      ? String(data.meta.samples_per_case)
      : "8";
  const cmd = `agentdiff compare --baseline ${baseRef} --samples ${samples}`;

  return (
    <div className="space-y-sm">
      <div className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
        Reproduction Command
      </div>
      <div className="flex items-center gap-sm border-2 border-node-border bg-canvas px-md py-sm">
        <code className="flex-1 font-mono text-small text-ink-light break-all">{cmd}</code>
        <CopyButton text={cmd} />
      </div>
    </div>
  );
}

// ── RunSummary section ────────────────────────────────────────────────────────
export function RunSummary({ data }: { data: ReportData }) {
  return (
    <div className="space-y-2xl">
      <div>
        <h1 className="font-mono text-h1 font-bold uppercase text-ink-light">Run Summary</h1>
        <p className="mt-xs text-small text-neutral-faint">
          Run quality, output evaluation details, and reproduction command.
        </p>
      </div>

      {/* Run quality */}
      <div className="space-y-md">
        <h2 className="font-mono text-h2 font-bold uppercase text-ink-light">Run Quality</h2>
        <div className="border-2 border-node-border bg-node-fill/30">
          <RunQualityTable data={data} />
        </div>
        <ThresholdsCard data={data} />
      </div>

      {/* Output evaluation */}
      <div className="space-y-md">
        <h2 className="font-mono text-h2 font-bold uppercase text-ink-light">
          Output Evaluation Details
        </h2>
        <p className="text-small text-neutral-faint">
          Traditional output-level metrics — semantic / structural similarity, length ratio, and
          LLM judge score. Note that these may pass even when behavioral deltas fail.
        </p>
        <div className="border-2 border-node-border bg-node-fill/30 overflow-x-auto">
          <OutputEvalTable evals={data.outputEvals} />
        </div>
      </div>

      {/* Reproduction */}
      <div className="space-y-md">
        <h2 className="font-mono text-h2 font-bold uppercase text-ink-light">Reproduction</h2>
        <ReproBlock data={data} />
      </div>
    </div>
  );
}

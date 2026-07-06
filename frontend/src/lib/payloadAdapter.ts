// Maps the raw JSON returned by `GET /v1/runs/{id}/payload` (the server's
// pass-through of `agentdiff.report_payload.build()` / `assemble_payload()`)
// onto the `ReportData` type the five report sections render against.
//
// Why an adapter instead of trusting the JSON verbatim: the payload is
// produced by a Python engine that has evolved across tasks (attribution
// `confidence`, output-eval `skipped_checks`, run-level `warnings`,
// `run_metrics`). Older stored runs may predate a field. This adapter fills
// safe defaults for every optional/new field so a stale or partial payload
// still renders instead of throwing, while a fresh payload passes every
// Task 6-8 field straight through.
import type {
  AgentGraph,
  Attribution,
  AttributionCause,
  AttributionConfidence,
  AttributionEntry,
  Comparison,
  GraphEdge,
  GraphNode,
  OutputEval,
  ReportData,
  RunMeta,
  RunMetricDelta,
  RunQuality,
  SkippedCheck,
  TestCaseComparison,
  Thresholds,
  Trajectories,
  TrajectorySummary,
  Verdict,
} from "@/types";

// ── Small helpers ────────────────────────────────────────────────────────────

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

function asString(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}

function asNumber(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function asBool(v: unknown, fallback = false): boolean {
  return typeof v === "boolean" ? v : fallback;
}

const VERDICTS: readonly Verdict[] = ["pass", "warn", "fail"];

function asVerdict(v: unknown, fallback: Verdict = "pass"): Verdict {
  const lower = typeof v === "string" ? v.toLowerCase() : "";
  return (VERDICTS as readonly string[]).includes(lower) ? (lower as Verdict) : fallback;
}

const CONFIDENCES: readonly AttributionConfidence[] = ["high", "medium", "low"];

/** Missing confidence (stale attribution artifacts predate this field) reads
 *  as "low" — the safest, least-asserting label per the brief's
 *  "low → low-confidence heuristic" framing. */
function asConfidence(v: unknown): AttributionConfidence {
  const lower = typeof v === "string" ? v.toLowerCase() : "";
  return (CONFIDENCES as readonly string[]).includes(lower)
    ? (lower as AttributionConfidence)
    : "low";
}

function asStringArray(v: unknown): string[] {
  return asArray(v).filter((x): x is string => typeof x === "string");
}

// ── graph ─────────────────────────────────────────────────────────────────

function mapGraphNode(raw: unknown): GraphNode | null {
  if (!isRecord(raw)) return null;
  const id = asString(raw.id);
  if (id === null) return null;
  return {
    id,
    label: asString(raw.label) ?? id,
    kind: raw.kind === "tool" ? "tool" : "agent",
    baseline_rate: asNumber(raw.baseline_rate) ?? 0,
    candidate_rate: asNumber(raw.candidate_rate) ?? 0,
    verdict: asVerdict(raw.verdict),
    fired: asBool(raw.fired),
    stopped: asBool(raw.stopped),
    cause_file: asString(raw.cause_file),
    hunk: asString(raw.hunk),
    explanation: asString(raw.explanation),
    significant: asBool(raw.significant),
  };
}

function mapGraphEdge(raw: unknown): GraphEdge | null {
  if (!isRecord(raw)) return null;
  const source = asString(raw.source);
  const target = asString(raw.target);
  if (source === null || target === null) return null;
  return { source, target };
}

function mapGraph(raw: unknown): AgentGraph {
  const rec = isRecord(raw) ? raw : {};
  return {
    nodes: asArray(rec.nodes)
      .map(mapGraphNode)
      .filter((n): n is GraphNode => n !== null),
    edges: asArray(rec.edges)
      .map(mapGraphEdge)
      .filter((e): e is GraphEdge => e !== null),
    overall_verdict: asVerdict(rec.overall_verdict),
    has_change: asBool(rec.has_change),
    min_samples: asNumber(rec.min_samples) ?? 0,
    has_uncertain: asBool(rec.has_uncertain),
  };
}

// ── meta / runQuality ────────────────────────────────────────────────────────

function mapMeta(raw: unknown): RunMeta {
  const rec = isRecord(raw) ? raw : {};
  return {
    baseline_ref: asString(rec.baseline_ref),
    candidate_ref: asString(rec.candidate_ref),
    samples_per_case:
      typeof rec.samples_per_case === "number" || typeof rec.samples_per_case === "string"
        ? rec.samples_per_case
        : null,
    timestamp: asString(rec.timestamp),
    smoke_mode: asBool(rec.smoke_mode),
  };
}

function mapThresholds(raw: unknown): Thresholds | null {
  if (!isRecord(raw)) return null;
  return {
    agent_invocation_rate_warn: asNumber(raw.agent_invocation_rate_warn) ?? 0,
    agent_invocation_rate_fail: asNumber(raw.agent_invocation_rate_fail) ?? 0,
    tool_usage_avg_warn: asNumber(raw.tool_usage_avg_warn) ?? 0,
    tool_usage_avg_fail: asNumber(raw.tool_usage_avg_fail) ?? 0,
    latency_ms_warn: asNumber(raw.latency_ms_warn) ?? undefined,
    latency_ms_fail: asNumber(raw.latency_ms_fail) ?? undefined,
    tokens_warn: asNumber(raw.tokens_warn) ?? undefined,
    tokens_fail: asNumber(raw.tokens_fail) ?? undefined,
    error_rate_warn: asNumber(raw.error_rate_warn) ?? undefined,
    error_rate_fail: asNumber(raw.error_rate_fail) ?? undefined,
  };
}

function mapRunQuality(raw: unknown): RunQuality {
  const rec = isRecord(raw) ? raw : {};
  return {
    baseline_trajectories: asNumber(rec.baseline_trajectories),
    candidate_trajectories: asNumber(rec.candidate_trajectories),
    baseline_failed: asNumber(rec.baseline_failed),
    candidate_failed: asNumber(rec.candidate_failed),
    max_failure_rate: asNumber(rec.max_failure_rate),
    thresholds: mapThresholds(rec.thresholds),
  };
}

// ── comparison (behavioral deltas + run metrics) ────────────────────────────

function mapRunMetricDelta(raw: unknown): RunMetricDelta | null {
  if (!isRecord(raw)) return null;
  const metric = raw.metric;
  if (metric !== "latency_ms" && metric !== "total_tokens" && metric !== "error_rate") {
    return null;
  }
  return {
    metric,
    baseline_mean: asNumber(raw.baseline_mean) ?? 0,
    candidate_mean: asNumber(raw.candidate_mean) ?? 0,
    delta: asNumber(raw.delta) ?? 0,
    p_value: asNumber(raw.p_value),
    adjusted_p_value: asNumber(raw.adjusted_p_value),
    verdict: asVerdict(raw.verdict),
    low_power: asBool(raw.low_power),
  };
}

function mapTestCaseComparison(raw: unknown): TestCaseComparison | null {
  if (!isRecord(raw)) return null;
  const testCaseId = asString(raw.test_case_id);
  if (testCaseId === null) return null;
  return {
    test_case_id: testCaseId,
    agent_invocation_deltas: asArray(raw.agent_invocation_deltas) as TestCaseComparison["agent_invocation_deltas"],
    tool_usage_deltas: asArray(raw.tool_usage_deltas) as TestCaseComparison["tool_usage_deltas"],
    run_metrics: asArray(raw.run_metrics)
      .map(mapRunMetricDelta)
      .filter((d): d is RunMetricDelta => d !== null),
    behavioral_overlap: asNumber(raw.behavioral_overlap),
    overall_verdict: asVerdict(raw.overall_verdict),
  };
}

function mapComparison(raw: unknown): Comparison | null {
  if (!isRecord(raw)) return null;
  return {
    test_case_comparisons: asArray(raw.test_case_comparisons)
      .map(mapTestCaseComparison)
      .filter((tc): tc is TestCaseComparison => tc !== null),
    overall_verdict: asVerdict(raw.overall_verdict),
    warnings: asStringArray(raw.warnings),
  };
}

// ── output evals ─────────────────────────────────────────────────────────────

function mapSkippedCheck(raw: unknown): SkippedCheck | null {
  if (!isRecord(raw)) return null;
  const check = asString(raw.check);
  if (check === null) return null;
  return { check, reason: asString(raw.reason) ?? "" };
}

function mapOutputEval(raw: unknown): OutputEval | null {
  if (!isRecord(raw)) return null;
  const testCaseId = asString(raw.test_case_id);
  if (testCaseId === null) return null;
  return {
    test_case_id: testCaseId,
    output_kind: asString(raw.output_kind) ?? "text",
    semantic_similarity: asNumber(raw.semantic_similarity),
    structural_similarity: asNumber(raw.structural_similarity),
    length_ratio: asNumber(raw.length_ratio),
    judge_score: asNumber(raw.judge_score),
    judge_reason: asString(raw.judge_reason),
    changed_keys: asStringArray(raw.changed_keys),
    verdict: asVerdict(raw.verdict),
    notes: asStringArray(raw.notes),
    // Older stored runs predate this field — absence means nothing was
    // skipped as far as we know, not that we should hide the column.
    skipped_checks: asArray(raw.skipped_checks)
      .map(mapSkippedCheck)
      .filter((s): s is SkippedCheck => s !== null),
  };
}

// ── attribution ───────────────────────────────────────────────────────────────

function mapAttributionCause(raw: unknown): AttributionCause | null {
  if (!isRecord(raw)) return null;
  return {
    rule: asString(raw.rule) ?? "unknown",
    target_path: asString(raw.target_path) ?? "",
    hunk: asString(raw.hunk),
    weight: asNumber(raw.weight) ?? 0,
    reason: asString(raw.reason) ?? "",
    // Stale attribution artifacts (pre-Task-6) don't carry `confidence` at
    // all — default to "low" so the UI reads it as a low-confidence
    // heuristic rather than crashing or silently claiming high confidence.
    confidence: asConfidence(raw.confidence),
  };
}

function mapAttributionEntry(raw: unknown): AttributionEntry | null {
  if (!isRecord(raw)) return null;
  const testCaseId = asString(raw.test_case_id);
  const agentName = asString(raw.agent_name);
  if (testCaseId === null || agentName === null) return null;
  return {
    test_case_id: testCaseId,
    agent_name: agentName,
    function: asString(raw.function) ?? "",
    metric: asString(raw.metric) ?? "",
    delta_summary: asString(raw.delta_summary) ?? "",
    verdict: asString(raw.verdict) ?? "fail",
    primary: mapAttributionCause(raw.primary),
    alternatives: asArray(raw.alternatives)
      .map(mapAttributionCause)
      .filter((c): c is AttributionCause => c !== null),
    explanation: asString(raw.explanation),
  };
}

function mapAttribution(raw: unknown): Attribution | null {
  if (!isRecord(raw)) return null;
  const attributions = asArray(raw.attributions)
    .map(mapAttributionEntry)
    .filter((a): a is AttributionEntry => a !== null);
  return { attributions };
}

// ── trajectories / timeline ──────────────────────────────────────────────────

function mapTrajectorySummary(raw: unknown): TrajectorySummary | null {
  if (!isRecord(raw)) return null;
  const trajectoryId = asString(raw.trajectory_id);
  const testCaseId = asString(raw.test_case_id);
  if (trajectoryId === null || testCaseId === null) return null;
  return {
    trajectory_id: trajectoryId,
    test_case_id: testCaseId,
    status: asString(raw.status) ?? "unknown",
    final_output: asString(raw.final_output),
    total_tokens: asNumber(raw.total_tokens) ?? 0,
    total_latency_ms: asNumber(raw.total_latency_ms) ?? 0,
    timeline: asArray(raw.timeline) as TrajectorySummary["timeline"],
  };
}

function mapTrajectories(raw: unknown): Trajectories {
  const rec = isRecord(raw) ? raw : {};
  return {
    baseline: asArray(rec.baseline)
      .map(mapTrajectorySummary)
      .filter((t): t is TrajectorySummary => t !== null),
    candidate: asArray(rec.candidate)
      .map(mapTrajectorySummary)
      .filter((t): t is TrajectorySummary => t !== null),
  };
}

// ── entry point ───────────────────────────────────────────────────────────────

/**
 * Maps the raw `GET /v1/runs/{id}/payload` JSON onto `ReportData`. Defensive
 * by construction: every field is optional-in, defaulted-out, so a partial or
 * stale stored payload still renders the five report sections instead of
 * throwing at the type boundary.
 */
export function toReportData(raw: unknown): ReportData {
  const rec = isRecord(raw) ? raw : {};
  const comparison = mapComparison(rec.comparison);

  // Run-level warnings live at the payload root (report_payload.build()
  // projects `comparison.warnings` up there too); fall back to the nested
  // copy for older/partial payloads that only set one of the two.
  const warnings = asStringArray(rec.warnings).length
    ? asStringArray(rec.warnings)
    : (comparison?.warnings ?? []);

  return {
    meta: mapMeta(rec.meta),
    runQuality: mapRunQuality(rec.runQuality),
    graph: mapGraph(rec.graph),
    comparison,
    warnings,
    outputEvals: asArray(rec.outputEvals)
      .map(mapOutputEval)
      .filter((e): e is OutputEval => e !== null),
    attribution: mapAttribution(rec.attribution),
    trajectories: mapTrajectories(rec.trajectories),
  };
}

// Mirrors the Python `agentdiff.report_payload.build()` output — the data
// contract between the engine and this dashboard. Every field here exists in a
// real `agentdiff compare` run (see docs/demo/sample-report/).

export type Verdict = "pass" | "warn" | "fail";

// ── Before/after agent graph (graph_model.AgentGraph) ──────────────────────
export interface GraphNode {
  id: string;
  label: string;
  kind: "agent" | "tool";
  baseline_rate: number; // agents: invocation rate; tools: avg calls/trajectory
  candidate_rate: number;
  verdict: Verdict;
  fired: boolean;
  stopped: boolean; // fired in baseline, gone in candidate — the ember signal
  cause_file: string | null;
  hunk: string | null;
  explanation: string | null;
  significant: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface AgentGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  overall_verdict: Verdict;
  has_change: boolean;
  min_samples: number;
  has_uncertain: boolean;
}

// ── Run metadata + quality ─────────────────────────────────────────────────
export interface Thresholds {
  agent_invocation_rate_warn: number;
  agent_invocation_rate_fail: number;
  tool_usage_avg_warn: number;
  tool_usage_avg_fail: number;
}

export interface RunMeta {
  baseline_ref?: string | null;
  candidate_ref?: string | null;
  samples_per_case?: number | string | null;
  timestamp?: string | null;
  smoke_mode?: boolean;
}

export interface RunQuality {
  baseline_trajectories: number | null;
  candidate_trajectories: number | null;
  baseline_failed: number | null;
  candidate_failed: number | null;
  max_failure_rate: number | null;
  thresholds: Thresholds | null;
}

// ── Behavioral comparison (compare.ComparisonResult) ───────────────────────
export interface AgentInvocationDelta {
  agent_name: string;
  function: string;
  baseline_rate: number;
  candidate_rate: number;
  delta: number;
  baseline_count: number;
  candidate_count: number;
  baseline_total: number;
  candidate_total: number;
  p_value: number | null;
  significant: boolean;
  verdict: Verdict;
}

export interface ToolUsageDelta {
  tool_name: string;
  baseline_avg: number;
  candidate_avg: number;
  delta: number;
  p_value: number | null;
  significant: boolean;
  verdict: Verdict;
}

export interface TestCaseComparison {
  test_case_id: string;
  agent_invocation_deltas: AgentInvocationDelta[];
  tool_usage_deltas: ToolUsageDelta[];
  behavioral_overlap: number | null;
  overall_verdict: Verdict;
}

export interface Comparison {
  test_case_comparisons: TestCaseComparison[];
  overall_verdict: Verdict;
}

// ── Output evaluation (output_eval.OutputEvalResult) ───────────────────────
export interface OutputEval {
  test_case_id: string;
  output_kind: string;
  semantic_similarity: number | null;
  structural_similarity: number | null;
  length_ratio: number | null;
  judge_score: number | null;
  changed_keys?: string[];
  verdict: Verdict;
  notes: string[];
}

// ── Causal attribution (attribution.engine.AttributionResult) ──────────────
export interface AttributionCause {
  rule: string;
  target_path: string;
  hunk: string | null;
  weight: number;
  reason: string;
}

export interface AttributionEntry {
  test_case_id: string;
  agent_name: string;
  function: string;
  metric: string;
  delta_summary: string;
  verdict: string;
  primary: AttributionCause | null;
  alternatives: AttributionCause[];
  explanation: string | null;
}

export interface Attribution {
  attributions: AttributionEntry[];
}

// ── Captured trajectories + timeline (report_payload._project_timeline) ────
export interface TimelineEvent {
  seq: number;
  kind: string; // llm_request | llm_response | local_tool_invoked | local_tool_returned | ...
  inferred_agent: string | null;
  provider: string | null;
  model: string | null;
  latency_ms: number | null;
  usage: Record<string, number> | null;
  tool_name: string | null;
  request_preview: string | null;
  response_preview: string | null;
}

export interface TrajectorySummary {
  trajectory_id: string;
  test_case_id: string;
  status: string;
  final_output: string | null;
  total_tokens: number;
  total_latency_ms: number;
  timeline: TimelineEvent[];
}

export interface Trajectories {
  baseline: TrajectorySummary[];
  candidate: TrajectorySummary[];
}

// ── The full payload ───────────────────────────────────────────────────────
export interface ReportData {
  meta: RunMeta;
  runQuality: RunQuality;
  graph: AgentGraph;
  comparison: Comparison | null;
  outputEvals: OutputEval[];
  attribution: Attribution | null;
  trajectories: Trajectories;
}

// Injected by the Python CLI as `window.__AGENTDIFF__`; falls back to the
// bundled real-run sample for `npm run dev`.
declare global {
  interface Window {
    __AGENTDIFF__?: ReportData;
  }
}

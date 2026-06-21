// Mirrors the Python `agentdiff.graph_model.AgentGraph` shape — the data
// contract between the engine and this dashboard.

export type Verdict = "pass" | "warn" | "fail";

export interface GraphNode {
  id: string;
  label: string;
  kind: "agent" | "tool";
  baseline_rate: number;
  candidate_rate: number;
  verdict: Verdict;
  fired: boolean;
  stopped: boolean;
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

export interface DashboardData {
  graph: AgentGraph;
  meta: {
    baseline_ref?: string;
    candidate_ref?: string;
    samples_per_case?: number | string;
    timestamp?: string;
  };
}

// Injected by the Python CLI as `window.__AGENTDIFF__`. Falls back to the
// bundled sample for `npm run dev`.
declare global {
  interface Window {
    __AGENTDIFF__?: DashboardData;
  }
}

import type { DashboardData } from "./types";

// Sample run used for `npm run dev` and the bundled `agentdiff dashboard --demo`.
// A four-agent pipeline where the orchestrator's prompt change stopped routing
// to fact_checker.
export const SAMPLE: DashboardData = {
  meta: {
    baseline_ref: "main",
    candidate_ref: "working tree",
    samples_per_case: 20,
    timestamp: "2026-06-21",
  },
  graph: {
    overall_verdict: "fail",
    has_change: true,
    nodes: [
      {
        id: "agent:orchestrator", label: "orchestrator", kind: "agent",
        baseline_rate: 1.0, candidate_rate: 1.0, verdict: "pass",
        fired: true, stopped: false, cause_file: null, hunk: null, explanation: null,
      },
      {
        id: "agent:fact_checker", label: "fact_checker", kind: "agent",
        baseline_rate: 0.9, candidate_rate: 0.0, verdict: "fail",
        fired: false, stopped: true,
        cause_file: "prompts/orchestrator.txt",
        hunk: "@@ -3,4 +3,3 @@\n You are an orchestrator.\n-Route to fact_checker when the answer\n-contains a factual claim that needs verification.\n+Answer directly and concisely.",
        explanation: "The orchestrator prompt no longer routes to fact_checker, so it stopped firing entirely.",
      },
      {
        id: "agent:summarizer", label: "summarizer", kind: "agent",
        baseline_rate: 0.85, candidate_rate: 0.95, verdict: "warn",
        fired: true, stopped: false,
        cause_file: null, hunk: null,
        explanation: null,
      },
      {
        id: "tool:web_search", label: "web_search", kind: "tool",
        baseline_rate: 2.1, candidate_rate: 3.4, verdict: "warn",
        fired: true, stopped: false, cause_file: null, hunk: null, explanation: null,
      },
      {
        id: "tool:retriever", label: "retriever", kind: "tool",
        baseline_rate: 1.0, candidate_rate: 1.0, verdict: "pass",
        fired: true, stopped: false, cause_file: null, hunk: null, explanation: null,
      },
    ],
    edges: [
      { source: "agent:orchestrator", target: "tool:web_search" },
      { source: "agent:orchestrator", target: "tool:retriever" },
      { source: "agent:fact_checker", target: "tool:web_search" },
      { source: "agent:summarizer", target: "tool:retriever" },
    ],
  },
};

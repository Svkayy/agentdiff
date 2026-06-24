// Single entry point for the report payload + small pure selectors the sections
// share. The CLI injects `window.__AGENTDIFF__`; dev falls back to the real sample.
import { SAMPLE } from "@/sample";
import type { AttributionEntry, ReportData, Verdict } from "@/types";

export function useReportData(): ReportData {
  return (typeof window !== "undefined" && window.__AGENTDIFF__) || SAMPLE;
}

/** Short, readable form of a git ref (40-char SHA → 7 chars; labels untouched). */
export function shortRef(ref?: string | null): string {
  if (!ref) return "working tree";
  return /^[0-9a-f]{40}$/i.test(ref) ? ref.slice(0, 7) : ref;
}

/** Tailwind-ready verdict color token (matches DESIGN.md). */
export function verdictColor(v: Verdict): string {
  return v === "fail" ? "ember" : v === "warn" ? "verdict-warn" : "verdict-pass";
}

/** One attribution per agent (the engine emits one per test case; collapse them,
 *  keeping the highest-confidence primary). */
export function dedupeAttributions(entries: AttributionEntry[]): AttributionEntry[] {
  const byAgent = new Map<string, AttributionEntry>();
  for (const e of entries) {
    const prev = byAgent.get(e.agent_name);
    const w = e.primary?.weight ?? 0;
    if (!prev || w > (prev.primary?.weight ?? 0)) byAgent.set(e.agent_name, e);
  }
  return [...byAgent.values()];
}

/** Count of flagged (non-pass) deltas across every test case. */
export function countFlaggedDeltas(data: ReportData): number {
  let n = 0;
  for (const tc of data.comparison?.test_case_comparisons ?? []) {
    n += tc.agent_invocation_deltas.filter((d) => d.verdict !== "pass").length;
    n += tc.tool_usage_deltas.filter((d) => d.verdict !== "pass").length;
  }
  return n;
}

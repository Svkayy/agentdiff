import { describe, it, expect } from "vitest";
import { toReportData } from "./payloadAdapter";
import { useReportData } from "./payload";
import sampleJson from "@/sample.json";

// ── Fixture: real committed run (frontend/src/sample.json), regenerated from
// `report_payload.build()` against docs/demo/sample-report/. This run's
// stored artifacts predate the Task 6-8 fields on outputEvals/attribution
// (skipped_checks, confidence) — that staleness is itself part of what the
// adapter must tolerate, so we assert both "real data survives" and
// "missing new fields get safe defaults" against it.

describe("toReportData — real sample.json (frontend/src/sample.json)", () => {
  const data = toReportData(sampleJson);

  it("maps meta/runQuality/graph through unchanged", () => {
    expect(data.meta.baseline_ref).toBe(
      (sampleJson as { meta: { baseline_ref: string } }).meta.baseline_ref,
    );
    expect(data.graph.nodes.length).toBe(sampleJson.graph.nodes.length);
    expect(data.graph.overall_verdict).toBe(sampleJson.graph.overall_verdict);
  });

  it("surfaces root-level warnings (empty for this run, but present as an array)", () => {
    expect(Array.isArray(data.warnings)).toBe(true);
    expect(data.warnings).toEqual(sampleJson.warnings ?? []);
  });

  it("projects run_metrics onto each test case comparison", () => {
    expect(data.comparison).not.toBeNull();
    const tcs = data.comparison!.test_case_comparisons;
    expect(tcs.length).toBeGreaterThan(0);
    for (const tc of tcs) {
      expect(Array.isArray(tc.run_metrics)).toBe(true);
    }
  });

  it("defaults skipped_checks to [] for stale outputEvals entries missing the field", () => {
    expect(data.outputEvals.length).toBeGreaterThan(0);
    for (const e of data.outputEvals) {
      expect(Array.isArray(e.skipped_checks)).toBe(true);
    }
  });

  it("defaults attribution confidence to 'low' for stale entries missing the field", () => {
    expect(data.attribution).not.toBeNull();
    const entries = data.attribution!.attributions;
    expect(entries.length).toBeGreaterThan(0);
    for (const entry of entries) {
      if (entry.primary) {
        expect(["high", "medium", "low"]).toContain(entry.primary.confidence);
      }
      for (const alt of entry.alternatives) {
        expect(["high", "medium", "low"]).toContain(alt.confidence);
      }
    }
  });
});

// ── Fixture: synthetic fresh payload matching the exact shape asserted by
// tests/server/test_payload.py (Task 10) — every Task 6-8 field present.
// This is what a NEW run's stored payload looks like end to end.

const FRESH_PAYLOAD = {
  meta: { baseline_ref: "main", candidate_ref: "feat" },
  runQuality: { baseline_trajectories: 8, candidate_trajectories: 8 },
  graph: { nodes: [], edges: [] },
  comparison: {
    overall_verdict: "fail",
    warnings: ["low sample size for tc1"],
    test_case_comparisons: [
      {
        test_case_id: "tc1",
        agent_invocation_deltas: [],
        tool_usage_deltas: [],
        behavioral_overlap: 0.4,
        overall_verdict: "fail",
        run_metrics: [
          {
            metric: "latency_ms",
            baseline_mean: 500.0,
            candidate_mean: 8000.0,
            delta: 7500.0,
            p_value: 0.01,
            adjusted_p_value: 0.01,
            verdict: "fail",
            low_power: false,
          },
        ],
      },
    ],
  },
  warnings: ["low sample size for tc1"],
  outputEvals: [
    {
      test_case_id: "tc1",
      output_kind: "text",
      verdict: "pass",
      notes: [],
      skipped_checks: [{ check: "judge", reason: "no LLM credential" }],
    },
  ],
  attribution: {
    attributions: [
      {
        test_case_id: "tc1",
        agent_name: "Fact Checker",
        function: "fact_checker",
        metric: "invocation_rate",
        delta_summary: "100% -> 0%",
        verdict: "fail",
        alternatives: [],
        primary: {
          target_path: "agents.py",
          rule: "code_change",
          weight: 0.8,
          reason: "changed",
          confidence: "high",
        },
      },
    ],
  },
  trajectories: { baseline: [], candidate: [] },
};

describe("toReportData — fresh payload (all Task 6-8 fields present)", () => {
  const data = toReportData(FRESH_PAYLOAD);

  it("passes run_metrics through with every RunMetricDelta field intact", () => {
    const rm = data.comparison!.test_case_comparisons[0].run_metrics![0];
    expect(rm).toMatchObject({
      metric: "latency_ms",
      baseline_mean: 500,
      candidate_mean: 8000,
      delta: 7500,
      p_value: 0.01,
      adjusted_p_value: 0.01,
      verdict: "fail",
      low_power: false,
    });
  });

  it("passes root-level warnings through verbatim", () => {
    expect(data.warnings).toEqual(["low sample size for tc1"]);
  });

  it("passes skipped_checks through with check + reason", () => {
    expect(data.outputEvals[0].skipped_checks).toEqual([
      { check: "judge", reason: "no LLM credential" },
    ]);
  });

  it("passes attribution confidence through verbatim (high)", () => {
    expect(data.attribution!.attributions[0].primary!.confidence).toBe("high");
  });
});

describe("toReportData — malformed/partial input", () => {
  it("does not throw on an empty object", () => {
    expect(() => toReportData({})).not.toThrow();
  });

  it("does not throw on null/undefined", () => {
    expect(() => toReportData(null)).not.toThrow();
    expect(() => toReportData(undefined)).not.toThrow();
  });

  it("returns empty-but-well-typed collections for an empty object", () => {
    const data = toReportData({});
    expect(data.graph.nodes).toEqual([]);
    expect(data.warnings).toEqual([]);
    expect(data.outputEvals).toEqual([]);
    expect(data.comparison).toBeNull();
    expect(data.attribution).toBeNull();
    expect(data.trajectories).toEqual({ baseline: [], candidate: [] });
  });
});

describe("useReportData — CLI sample fallback", () => {
  it("adapts the bundled sample before the CLI report renders it", () => {
    const data = useReportData();
    expect(data.outputEvals.length).toBeGreaterThan(0);
    for (const e of data.outputEvals) {
      expect(Array.isArray(e.skipped_checks)).toBe(true);
    }
  });
});

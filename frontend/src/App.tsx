import { useMemo, useState } from "react";
import { AgentGraph } from "@/components/AgentGraph";
import { AIExplainer } from "@/components/AIExplainer";
import { Inspector } from "@/components/Inspector";
import { TopNav } from "@/components/TopNav";
import { Footer } from "@/components/Footer";
import { SAMPLE } from "./sample";
import type { GraphNode } from "@/types";

export default function App() {
  const data = window.__AGENTDIFF__ ?? SAMPLE;
  const { graph, meta } = data;

  const firstStopped = useMemo(
    () => graph.nodes.find((n) => n.stopped) ?? graph.nodes.find((n) => n.hunk) ?? null,
    [graph],
  );
  const [selected, setSelected] = useState<GraphNode | null>(firstStopped);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-50 text-text-main">
      <TopNav
        verdict={graph.overall_verdict}
        baselineRef={String(meta.baseline_ref ?? "main")}
        candidateRef={String(meta.candidate_ref ?? "working tree")}
      />

      <div className="relative flex flex-1 overflow-hidden">
        <main className="relative flex-1 overflow-hidden bg-slate-50">
          <AgentGraph graph={graph} selectedId={selected?.id ?? null} onSelect={setSelected} />
          <AIExplainer node={selected} />
        </main>
        <Inspector node={selected} />
      </div>

      <Footer graph={graph} verdict={graph.overall_verdict} />
    </div>
  );
}

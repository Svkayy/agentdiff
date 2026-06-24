import { useState } from "react";
import { cn } from "@/lib/utils";
import type { TimelineEvent } from "@/types";

// Per-agent color chips (same set used across both sides for consistency)
const AGENT_COLORS: Record<string, string> = {
  orchestrator: "bg-[#4A6CF7]/20 text-[#7B96F8] border-[#4A6CF7]/30",
  retriever: "bg-[#3FB27F]/20 text-[#3FB27F] border-[#3FB27F]/30",
  fact_checker: "bg-ember/20 text-ember border-ember/30",
  summarizer: "bg-[#E8A33D]/20 text-[#E8A33D] border-[#E8A33D]/30",
};

const DEFAULT_AGENT_COLOR = "bg-node-fill text-neutral-faint border-node-border";

function agentColor(agent: string | null): string {
  if (!agent) return DEFAULT_AGENT_COLOR;
  return AGENT_COLORS[agent] ?? DEFAULT_AGENT_COLOR;
}

// Kind glyphs
function KindGlyph({ kind }: { kind: string }) {
  if (kind === "llm_request") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full border border-node-border bg-node-fill font-mono text-micro text-neutral-faint">
        ↑
      </span>
    );
  }
  if (kind === "llm_response") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full border border-node-border bg-node-fill font-mono text-micro text-neutral-faint">
        ↓
      </span>
    );
  }
  if (kind === "local_tool_invoked") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full border border-verdict-warn/30 bg-verdict-warn/10 font-mono text-micro text-verdict-warn">
        ⚙
      </span>
    );
  }
  if (kind === "local_tool_returned") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full border border-verdict-warn/30 bg-verdict-warn/10 font-mono text-micro text-verdict-warn">
        ✓
      </span>
    );
  }
  return (
    <span className="flex h-5 w-5 items-center justify-center rounded-full border border-node-border bg-node-fill font-mono text-micro text-neutral-faint">
      ·
    </span>
  );
}

function truncate(s: string | null, max = 120): string {
  if (!s) return "";
  return s.length > max ? s.slice(0, max) + "…" : s;
}

export function EventRow({ event }: { event: TimelineEvent }) {
  const [expanded, setExpanded] = useState(false);
  const hasPreview = event.request_preview || event.response_preview;
  const isLLM = event.kind === "llm_request" || event.kind === "llm_response";
  const isTool = event.kind === "local_tool_invoked" || event.kind === "local_tool_returned";

  return (
    <div
      className={cn(
        "rounded-sm border border-node-border bg-node-fill/30 px-md py-sm transition-colors",
        hasPreview && "cursor-pointer hover:bg-node-fill/60",
      )}
      onClick={() => hasPreview && setExpanded((v) => !v)}
    >
      <div className="flex items-center gap-sm">
        {/* Seq */}
        <span className="w-6 shrink-0 font-mono text-micro text-neutral-faint tabular-nums text-right">
          {event.seq}
        </span>

        {/* Kind glyph */}
        <KindGlyph kind={event.kind} />

        {/* Agent chip */}
        <span
          className={cn(
            "shrink-0 rounded-sm border px-xs py-2xs font-mono text-micro",
            agentColor(event.inferred_agent),
          )}
        >
          {event.inferred_agent ?? "—"}
        </span>

        {/* Tool name for tool events */}
        {isTool && event.tool_name && (
          <span className="font-mono text-small text-ink-light">{event.tool_name}</span>
        )}

        {/* Provider / model for LLM events */}
        {isLLM && event.model && (
          <span className="hidden font-mono text-micro text-neutral-faint sm:inline truncate max-w-[120px]">
            {event.model}
          </span>
        )}

        {/* Latency + tokens */}
        <div className="ml-auto flex shrink-0 items-center gap-sm">
          {event.latency_ms !== null && (
            <span className="font-mono text-micro tabular-nums text-neutral-faint">
              {event.latency_ms.toFixed(0)}ms
            </span>
          )}
          {event.usage && (
            <span className="font-mono text-micro tabular-nums text-neutral-faint">
              {event.usage.total_tokens ?? 0}tok
            </span>
          )}
          {hasPreview && (
            <span className="font-mono text-micro text-neutral-faint">
              {expanded ? "▲" : "▼"}
            </span>
          )}
        </div>
      </div>

      {/* Expanded preview */}
      {expanded && (
        <div className="mt-sm space-y-xs">
          {event.request_preview && (
            <div>
              <div className="mb-2xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
                Request
              </div>
              <pre className="overflow-x-auto rounded-sm bg-canvas p-sm font-mono text-micro text-ink-light whitespace-pre-wrap leading-relaxed">
                {truncate(event.request_preview, 300)}
              </pre>
            </div>
          )}
          {event.response_preview && (
            <div>
              <div className="mb-2xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
                Response
              </div>
              <pre className="overflow-x-auto rounded-sm bg-canvas p-sm font-mono text-micro text-ink-light whitespace-pre-wrap leading-relaxed">
                {truncate(event.response_preview, 300)}
              </pre>
            </div>
          )}
          {isTool && event.request_preview && (
            <div>
              <div className="mb-2xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
                Args
              </div>
              <pre className="overflow-x-auto rounded-sm bg-canvas p-sm font-mono text-micro text-ink-light whitespace-pre-wrap leading-relaxed">
                {truncate(event.request_preview, 300)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

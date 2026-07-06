import { useEffect, useState } from "react";

// Capture shims AgentDiff ships — httpx / requests / aiohttp transport shims
// plus the OpenAI / Anthropic SDK shims. All ACTIVE (they exist in-tree).
const SHIMS = [
  { name: "httpx", kind: "TRANSPORT", status: "ACTIVE" },
  { name: "requests", kind: "TRANSPORT", status: "ACTIVE" },
  { name: "aiohttp", kind: "TRANSPORT", status: "ACTIVE" },
  { name: "openai-sdk", kind: "SDK", status: "ACTIVE" },
  { name: "anthropic-sdk", kind: "SDK", status: "ACTIVE" },
];

/**
 * Bento status card — ported from the template's `status-card.tsx`, retargeted
 * to AgentDiff's capture-shim inventory. The bottom bar is a clearly-decorative
 * "coverage" indicator (a static, ornamental fill — not a live metric).
 */
export function StatusCard() {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setTick((t) => t + 1);
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between border-b-2 border-foreground px-4 py-2">
        <span className="text-[11px] tracking-widest text-muted-foreground uppercase">
          capture_shims.status
        </span>
        <span className="text-[11px] tracking-widest text-muted-foreground">
          {`TICK:${String(tick).padStart(4, "0")}`}
        </span>
      </div>
      <div className="flex-1 flex flex-col p-4 gap-0">
        {/* Table header */}
        <div className="grid grid-cols-3 gap-2 border-b border-border pb-2 mb-2">
          <span className="text-[11px] tracking-[0.12em] uppercase text-muted-foreground">Shim</span>
          <span className="text-[11px] tracking-[0.12em] uppercase text-muted-foreground">Kind</span>
          <span className="text-[11px] tracking-[0.12em] uppercase text-muted-foreground text-right">
            Status
          </span>
        </div>
        {SHIMS.map((shim) => (
          <div
            key={shim.name}
            className="grid grid-cols-3 gap-2 py-1.5 border-b border-border last:border-none"
          >
            <span className="text-sm font-mono text-foreground">{shim.name}</span>
            <span className="text-sm font-mono text-foreground/70">{shim.kind}</span>
            <div className="flex items-center justify-end gap-2">
              <span className="h-1.5 w-1.5 bg-[#ea580c]" />
              <span className="text-sm font-mono text-foreground/70">{shim.status}</span>
            </div>
          </div>
        ))}
        {/* Decorative coverage bar (ornamental, not a live metric) */}
        <div className="mt-auto pt-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] tracking-[0.12em] uppercase text-muted-foreground">
              Capture Coverage
            </span>
            <span className="text-[11px] font-mono text-foreground">zero-config</span>
          </div>
          <div className="h-2 w-full border border-foreground">
            <div className="h-full bg-foreground" style={{ width: "100%" }} />
          </div>
        </div>
      </div>
    </div>
  );
}

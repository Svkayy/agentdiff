// Renders a unified diff hunk with per-line coloring.
// Added (+) lines: faint green tint
// Removed (-) lines: faint ember tint
// Context: neutral
import { cn } from "@/lib/utils";

interface DiffHunkProps {
  hunk: string;
  className?: string;
}

function classifyLine(line: string): "added" | "removed" | "header" | "context" {
  if (line.startsWith("+") && !line.startsWith("+++")) return "added";
  if (line.startsWith("-") && !line.startsWith("---")) return "removed";
  if (line.startsWith("@@") || line.startsWith("diff ") || line.startsWith("index ")) {
    return "header";
  }
  return "context";
}

export function DiffHunk({ hunk, className }: DiffHunkProps) {
  const lines = hunk.split("\n");
  return (
    <div
      className={cn(
        "overflow-x-auto border-2 border-node-border bg-canvas p-md font-mono text-micro leading-relaxed",
        className,
      )}
    >
      {lines.map((line, i) => {
        const kind = classifyLine(line);
        // Removed lines carry the orange signal (they're what regressed);
        // added lines use a distinguishable calm green; both stay legible on
        // the dark terminal plate.
        const lineClass =
          kind === "added"
            ? "text-[#4c9a6a] bg-[#4c9a6a]/10"
            : kind === "removed"
              ? "text-[#ea580c] bg-[#ea580c]/10"
              : kind === "header"
                ? "text-neutral-faint"
                : "text-ink-light";
        return (
          <div key={i} className={`whitespace-pre px-xs ${lineClass}`}>
            {line || " "}
          </div>
        );
      })}
    </div>
  );
}

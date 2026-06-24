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
        "overflow-x-auto rounded-sm bg-canvas p-md font-mono text-micro leading-relaxed",
        className,
      )}
    >
      {lines.map((line, i) => {
        const kind = classifyLine(line);
        const lineClass =
          kind === "added"
            ? "text-verdict-pass/90 bg-verdict-pass/5"
            : kind === "removed"
              ? "text-ember/90 bg-ember/5"
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

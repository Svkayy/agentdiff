import { Github } from "lucide-react";

const LINKS = [
  { label: "How it works", href: "#how-it-works" },
  { label: "Integrations", href: "#integrations" },
  { label: "Docs", href: "https://github.com/sandeepvinay/agentdiff#documentation" },
];

export function Nav() {
  return (
    <header className="sticky top-0 z-50 border-b border-hairline bg-shell/95 backdrop-blur-none">
      <nav
        aria-label="Primary"
        className="mx-auto flex h-14 max-w-content items-center justify-between px-5"
      >
        <a href="#top" className="flex items-baseline gap-2" aria-label="AgentDiff home">
          <span className="font-mono text-sm font-medium text-ink">Δ</span>
          <span className="font-display text-lg font-bold tracking-tight text-ink">
            AgentDiff
          </span>
        </a>
        <div className="flex items-center gap-6">
          {LINKS.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="hidden text-sm text-muted transition-colors duration-200 hover:text-ink sm:inline"
            >
              {l.label}
            </a>
          ))}
          <a
            href="https://github.com/sandeepvinay/agentdiff"
            className="inline-flex items-center gap-2 rounded-sm border border-hairline bg-card px-3 py-1.5 text-sm text-ink transition-colors duration-200 hover:border-faint"
          >
            <Github className="h-4 w-4" aria-hidden="true" />
            GitHub
          </a>
        </div>
      </nav>
    </header>
  );
}

import { Link } from "react-router-dom";
import { Github } from "lucide-react";

// Section links point at the marketing home anchors; docs is a real route.
const LINKS = [
  { label: "How it works", href: "/#how-it-works" },
  { label: "Integrations", href: "/#integrations" },
  { label: "Docs", href: "/docs" },
];

export function Nav() {
  return (
    <header className="sticky top-0 z-50 border-b border-hairline bg-shell/95 backdrop-blur-none">
      <nav
        aria-label="Primary"
        className="mx-auto flex h-14 max-w-content items-center justify-between px-5"
      >
        <Link to="/" className="flex items-baseline gap-2" aria-label="AgentDiff home">
          <span className="font-mono text-sm font-medium text-ink">Δ</span>
          <span className="font-display text-lg font-bold tracking-tight text-ink">
            AgentDiff
          </span>
        </Link>
        <div className="flex items-center gap-4 sm:gap-6">
          {LINKS.map((l) =>
            l.href.startsWith("/#") ? (
              <a
                key={l.label}
                href={l.href}
                className="hidden text-sm text-muted transition-colors duration-200 hover:text-ink sm:inline"
              >
                {l.label}
              </a>
            ) : (
              <Link
                key={l.label}
                to={l.href}
                className="hidden text-sm text-muted transition-colors duration-200 hover:text-ink sm:inline"
              >
                {l.label}
              </Link>
            ),
          )}
          <a
            href="https://github.com/sandeepvinay/agentdiff"
            className="hidden items-center gap-2 rounded-sm border border-hairline bg-card px-3 py-1.5 text-sm text-ink transition-colors duration-200 hover:border-faint sm:inline-flex"
            aria-label="AgentDiff on GitHub"
          >
            <Github className="h-4 w-4" aria-hidden="true" />
            GitHub
          </a>
          <Link
            to="/projects"
            className="hidden text-sm text-muted transition-colors duration-200 hover:text-ink sm:inline"
          >
            Sign in
          </Link>
          <Link
            to="/projects"
            className="inline-flex items-center rounded-sm border border-ink bg-ink px-3 py-1.5 text-sm font-medium text-shell transition-colors duration-200 hover:bg-[#22262D]"
          >
            Get started
          </Link>
        </div>
      </nav>
    </header>
  );
}

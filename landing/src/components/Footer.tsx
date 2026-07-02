export function Footer() {
  return (
    <footer className="bg-shell">
      <div className="mx-auto flex max-w-content flex-col items-start justify-between gap-4 px-5 py-10 sm:flex-row sm:items-center">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-sm text-ink">Δ</span>
          <span className="font-display text-base font-bold text-ink">AgentDiff</span>
          <span className="ml-2 text-sm text-muted">
            Behavioral regression testing for AI agent systems.
          </span>
        </div>
        <div className="flex items-center gap-6 text-sm text-muted">
          <span className="font-mono text-[12px]">MIT License</span>
          <a
            href="https://github.com/sandeepvinay/agentdiff"
            className="transition-colors duration-200 hover:text-ink"
          >
            GitHub
          </a>
          <a
            href="https://github.com/sandeepvinay/agentdiff#documentation"
            className="transition-colors duration-200 hover:text-ink"
          >
            Docs
          </a>
        </div>
      </div>
    </footer>
  );
}

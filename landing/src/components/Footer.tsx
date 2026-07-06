// Contact inbox is a placeholder — a real security@ inbox must be provisioned
// before launch (documented in the task report). See also privacy/terms.
const CONTACT_EMAIL = "security@agentdiff.dev";

const LINKS: { label: string; href: string }[] = [
  { label: "Docs", href: "#/docs" },
  { label: "Privacy", href: "#/privacy" },
  { label: "Terms", href: "#/terms" },
  { label: "Contact", href: `mailto:${CONTACT_EMAIL}` },
  { label: "Issues", href: "https://github.com/sandeepvinay/agentdiff/issues" },
  { label: "GitHub", href: "https://github.com/sandeepvinay/agentdiff" },
];

export function Footer() {
  return (
    <footer className="border-t border-hairline bg-shell">
      <div className="mx-auto flex max-w-content flex-col items-start justify-between gap-4 px-5 py-10 sm:flex-row sm:items-center">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-sm text-ink">Δ</span>
          <span className="font-display text-base font-bold text-ink">AgentDiff</span>
          <span className="ml-2 hidden text-sm text-muted sm:inline">
            Behavioral regression testing for AI agent systems.
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-muted">
          <span className="font-mono text-[12px]">MIT License</span>
          {LINKS.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="transition-colors duration-200 hover:text-ink"
            >
              {l.label}
            </a>
          ))}
        </div>
      </div>
    </footer>
  );
}

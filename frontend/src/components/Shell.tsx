import type { ReactNode } from "react";
import { Link, useMatch } from "react-router-dom";
import { UserButton } from "@clerk/clerk-react";

interface ShellProps {
  children: ReactNode;
}

export function Shell({ children }: ShellProps) {
  const onProjects = useMatch("/");

  return (
    <div className="flex h-screen flex-col bg-shell-bg text-ink-dark">
      {/* ── Top bar ──────────────────────────────────────────────────────── */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-hairline bg-white px-xl">
        <div className="flex items-center gap-md">
          <Link
            to="/"
            className="font-display text-h2 font-bold tracking-tight text-ink-dark"
          >
            AgentDiff
          </Link>
          {!onProjects && (
            <>
              <span className="h-4 w-px bg-hairline" />
              <Link
                to="/"
                className="text-small text-neutral-muted transition-colors hover:text-ink-dark"
              >
                Projects
              </Link>
            </>
          )}
        </div>
        <div className="flex items-center gap-md">
          <UserButton afterSignOutUrl="/" />
        </div>
      </header>

      {/* ── Content ──────────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}

import { type ReactNode, useEffect, useState } from "react";
import { Link, useMatch } from "react-router-dom";
import { UserButton, useAuth } from "@clerk/clerk-react";
import { fetchMe } from "@/lib/api";

interface ShellProps {
  children: ReactNode;
}

export function Shell({ children }: ShellProps) {
  const onProjects = useMatch("/projects");
  const { getToken } = useAuth();
  const [orgName, setOrgName] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMe(getToken)
      .then((me) => {
        if (!cancelled) setOrgName(me.org?.name ?? null);
      })
      .catch(() => {
        /* header org name is non-critical — leave blank on failure */
      });
    return () => {
      cancelled = true;
    };
  }, [getToken]);

  return (
    <div className="flex h-screen flex-col bg-shell-bg text-ink-dark">
      {/* ── Top bar ──────────────────────────────────────────────────────── */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-hairline bg-white px-xl">
        <div className="flex items-center gap-md">
          <Link
            to="/projects"
            className="font-display text-h2 font-bold tracking-tight text-ink-dark"
          >
            AgentDiff
          </Link>
          {!onProjects && (
            <>
              <span className="h-4 w-px bg-hairline" />
              <Link
                to="/projects"
                className="text-small text-neutral-muted transition-colors hover:text-ink-dark"
              >
                Projects
              </Link>
            </>
          )}
        </div>
        <div className="flex items-center gap-md">
          {orgName && (
            <span className="hidden items-center gap-xs font-mono text-micro uppercase tracking-widest text-neutral-faint sm:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-verdict-pass" />
              {orgName}
            </span>
          )}
          {/* Intentional: signed-out users land on the marketing home, not /projects */}
          <UserButton afterSignOutUrl="/" />
        </div>
      </header>

      {/* ── Content ──────────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}

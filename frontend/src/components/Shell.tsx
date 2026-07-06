import { type ReactNode, useEffect, useState } from "react";
import { Link, useMatch } from "react-router-dom";
import { UserButton, useAuth } from "@clerk/clerk-react";
import { GitCompareArrows } from "lucide-react";
import { fetchMe } from "@/lib/api";
import { ThemeToggle } from "@/components/system/ThemeToggle";

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
    <div className="flex h-screen flex-col bg-background text-foreground">
      {/* ── Top bar (bordered navbar per DESIGN.md) ──────────────────────── */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b-2 border-foreground bg-background px-xl">
        <div className="flex items-center gap-md">
          <Link
            to="/projects"
            className="flex items-center gap-sm font-mono text-xs font-bold uppercase tracking-[0.15em] text-foreground"
          >
            <GitCompareArrows size={16} strokeWidth={1.5} aria-hidden="true" />
            AGENTDIFF
          </Link>
          {!onProjects && (
            <>
              <span className="h-4 w-px bg-border" />
              <Link
                to="/projects"
                className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground transition-colors hover:text-foreground"
              >
                Projects
              </Link>
            </>
          )}
        </div>
        <div className="flex items-center gap-md">
          {orgName && (
            <span className="hidden items-center gap-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground sm:flex">
              <span className="h-1.5 w-1.5 bg-[#ea580c]" aria-hidden="true" />
              {orgName}
            </span>
          )}
          <ThemeToggle />
          {/* Intentional: signed-out users land on the marketing home, not /projects */}
          <UserButton afterSignOutUrl="/" />
        </div>
      </header>

      {/* ── Content ──────────────────────────────────────────────────────── */}
      <main className="dot-grid-bg flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}

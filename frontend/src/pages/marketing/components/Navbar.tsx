import { Link } from "react-router-dom";
import { Cpu } from "lucide-react";
import { motion } from "framer-motion";
import { ThemeToggle } from "@/components/system/ThemeToggle";
import { PUBLIC_DASHBOARD_CTA, PUBLIC_SIGN_IN_CTA } from "@/lib/publicCtas";

const ease = [0.22, 1, 0.36, 1] as const;

const GITHUB_URL = "https://github.com/Svkayy/agentdiff";

// Center links: Docs is a real route, GitHub is the external repo.
const LINKS: { label: string; href: string; kind: "route" | "anchor" | "external" }[] = [
  { label: "Demo", href: "/demo", kind: "route" },
  { label: "Docs", href: "/docs", kind: "route" },
  { label: "GitHub", href: GITHUB_URL, kind: "external" },
];

/**
 * Brutalist top bar — ported from the reference template's `navbar.tsx`.
 * Bordered rectangle, Cpu mark + AGENTDIFF wordmark, center mono links,
 * ThemeToggle, and a solid public CTA.
 */
export function Navbar() {
  return (
    <motion.div
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease }}
      className="w-full px-4 pt-4 lg:px-6 lg:pt-6"
    >
      <nav className="w-full border border-foreground/20 bg-background/80 backdrop-blur-sm px-6 py-3 lg:px-8">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2, duration: 0.4 }}
          >
            <Link to="/" className="flex items-center gap-3" aria-label="AgentDiff home">
              <Cpu size={16} strokeWidth={1.5} />
              <span className="text-xs font-mono tracking-[0.15em] uppercase font-bold">
                AGENTDIFF
              </span>
            </Link>
          </motion.div>

          {/* Center nav links */}
          <div className="hidden md:flex items-center gap-8">
            {LINKS.map((link, i) => {
              const cls =
                "text-xs font-mono tracking-widest uppercase text-muted-foreground hover:text-foreground transition-colors duration-200";
              const anim = {
                initial: { opacity: 0, y: -8 },
                animate: { opacity: 1, y: 0 },
                transition: { delay: 0.3 + i * 0.06, duration: 0.4, ease },
              };
              if (link.kind === "route") {
                return (
                  <motion.div key={link.label} {...anim}>
                    <Link to={link.href} className={cls}>
                      {link.label}
                    </Link>
                  </motion.div>
                );
              }
              return (
                <motion.a
                  key={link.label}
                  href={link.href}
                  {...(link.kind === "external"
                    ? { target: "_blank", rel: "noreferrer noopener" }
                    : {})}
                  {...anim}
                  className={cls}
                >
                  {link.label}
                </motion.a>
              );
            })}
          </div>

          {/* Right side: ThemeToggle + CTA */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5, duration: 0.4 }}
            className="flex items-center gap-4"
          >
            <ThemeToggle />
            {PUBLIC_SIGN_IN_CTA && (
              <Link
                to={PUBLIC_SIGN_IN_CTA.path}
                className="hidden sm:block text-xs font-mono tracking-widest uppercase text-muted-foreground hover:text-foreground transition-colors duration-200"
              >
                {PUBLIC_SIGN_IN_CTA.label}
              </Link>
            )}
            <Link to={PUBLIC_DASHBOARD_CTA.path}>
              <motion.span
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="inline-block bg-foreground text-background px-4 py-2 text-xs font-mono tracking-widest uppercase"
              >
                {PUBLIC_DASHBOARD_CTA.label}
              </motion.span>
            </Link>
          </motion.div>
        </div>
      </nav>
    </motion.div>
  );
}

import { Link } from "react-router-dom";
import { motion } from "framer-motion";

const ease = [0.22, 1, 0.36, 1] as const;

const GITHUB_URL = "https://github.com/Svkayy/agentdiff";

const LINKS: { label: string; href: string; kind: "route" | "external" }[] = [
  { label: "Demo", href: "/demo", kind: "route" },
  { label: "Privacy", href: "/privacy", kind: "route" },
  { label: "Terms", href: "/terms", kind: "route" },
  { label: "Docs", href: "/docs", kind: "route" },
  { label: "GitHub", href: GITHUB_URL, kind: "external" },
];

/**
 * Brutalist footer — ported from the template's `footer.tsx`. AGENTDIFF
 * wordmark + (C) 2026 and the real Privacy / Terms / Docs / GitHub routes.
 */
export function BrutalistFooter() {
  return (
    <motion.footer
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.6, ease }}
      className="w-full border-t-2 border-foreground px-6 py-8 lg:px-12"
    >
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-mono tracking-[0.15em] uppercase font-bold text-foreground">
            AGENTDIFF
          </span>
          <span className="text-[11px] font-mono tracking-widest text-muted-foreground">
            {"(C) 2026 AGENTDIFF · MIT LICENSE"}
          </span>
        </div>
        <div className="flex items-center gap-6">
          {LINKS.map((link, i) => {
            const cls =
              "text-[11px] font-mono tracking-widest uppercase text-muted-foreground hover:text-foreground transition-colors duration-200";
            const anim = {
              initial: { opacity: 0, y: 6 },
              whileInView: { opacity: 1, y: 0 },
              viewport: { once: true },
              transition: { delay: 0.1 + i * 0.06, duration: 0.4, ease },
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
                target="_blank"
                rel="noreferrer noopener"
                {...anim}
                className={cls}
              >
                {link.label}
              </motion.a>
            );
          })}
        </div>
      </div>
    </motion.footer>
  );
}

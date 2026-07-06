// Docs registry — the in-app documentation index for the landing site.
//
// Source of truth for doc BODIES is the repo's `docs/**/*.md`, pulled in at
// build time via import.meta.glob so the single-file GH-Pages bundle stays
// self-contained (no runtime fetches, no server). Some entries below may be
// authored by concurrent tasks and not exist yet (e.g. deploy-production) —
// the registry is deliberately TOLERANT: the sidebar is derived from the
// curated list filtered to globs that actually resolved, so a missing/renamed
// doc never breaks the build. A later integration task re-verifies
// completeness.
//
// privacy/terms are the two legal docs authored HERE (src/content/*.md).
// security is the repo-root SECURITY.md (outside docs/, so it has its own
// glob below). All three are merged into the Policies group.

// Eagerly import every markdown doc in the repo docs tree as raw text.
const repoDocs = import.meta.glob("../../../docs/**/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

// Legal docs live inside the landing app so they ship with the marketing site
// even when the repo docs tree is absent.
const legalDocs = import.meta.glob("../content/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

// The repo-root SECURITY.md is outside the docs/ tree, so it needs its own
// glob. Kept as a narrow, explicit pattern (not a broad repo-root glob) so we
// don't accidentally pull in unrelated root-level markdown (README, etc).
const rootDocs = import.meta.glob("../../../SECURITY.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** A single doc, resolved and ready to render. */
export interface DocEntry {
  slug: string;
  title: string;
  markdown: string;
  group: string;
}

/** A sidebar group with its resolved docs (empty groups are dropped). */
export interface DocGroup {
  title: string;
  docs: DocEntry[];
}

// Curated navigation. `file` is matched against the tail of a glob key, so it
// is order-independent of the exact glob prefix. `title` is the sidebar label.
interface NavItem {
  slug: string;
  title: string;
  file: string; // path fragment that must appear at the end of a source key
}
interface NavGroup {
  title: string;
  items: NavItem[];
}

const NAV: NavGroup[] = [
  {
    title: "Getting Started",
    items: [
      {
        slug: "getting-started",
        title: "Your First Comparison",
        file: "docs/tutorial-getting-started.md",
      },
    ],
  },
  {
    title: "Guides",
    items: [
      {
        slug: "interpret-report",
        title: "Interpret a Report",
        file: "docs/howto-interpret-report.md",
      },
      { slug: "integrations", title: "Integrations", file: "docs/integrations.md" },
      {
        slug: "ci-troubleshooting",
        title: "CI Troubleshooting",
        file: "docs/recipes/ci-troubleshooting.md",
      },
      {
        slug: "hosted-quickstart",
        title: "Hosted Quickstart",
        file: "docs/hosted-quickstart.md",
      },
      {
        slug: "deploy-production",
        title: "Deploy to Production",
        file: "docs/deploy-production.md",
      },
      { slug: "data-handling", title: "Data Handling", file: "docs/data-handling.md" },
    ],
  },
  {
    title: "Reference",
    items: [
      {
        slug: "reference-config",
        title: "Configuration",
        file: "docs/reference-config.md",
      },
      { slug: "methodology", title: "Methodology", file: "docs/METHODOLOGY.md" },
      { slug: "codebase", title: "Codebase Map", file: "docs/CODEBASE.md" },
    ],
  },
  {
    title: "Recipes",
    items: [
      { slug: "runner-recipes", title: "Runner Recipes", file: "docs/recipes/README.md" },
      { slug: "limitations", title: "Limitations", file: "docs/recipes/limitations.md" },
      {
        slug: "why-behavioral",
        title: "Why Behavioral?",
        file: "docs/explanation-why-behavioral.md",
      },
    ],
  },
  {
    title: "Policies",
    items: [
      { slug: "privacy", title: "Privacy Policy", file: "content/privacy.md" },
      { slug: "terms", title: "Terms of Service", file: "content/terms.md" },
      { slug: "security", title: "Security Policy", file: "SECURITY.md" },
    ],
  },
];

/** All raw sources keyed by their glob path, from all three roots. */
const allSources: Record<string, string> = {
  ...repoDocs,
  ...legalDocs,
  ...rootDocs,
};

/** Find the raw markdown for a nav item, or undefined if it did not resolve. */
function resolveSource(file: string): string | undefined {
  const key = Object.keys(allSources).find((k) => k.endsWith(file));
  return key ? allSources[key] : undefined;
}

// Build the resolved registry: only nav items whose source resolved survive,
// and only non-empty groups are kept.
const groups: DocGroup[] = [];
for (const group of NAV) {
  const docs: DocEntry[] = [];
  for (const item of group.items) {
    const markdown = resolveSource(item.file);
    if (markdown === undefined) continue; // tolerant: skip missing docs
    docs.push({
      slug: item.slug,
      title: item.title,
      markdown,
      group: group.title,
    });
  }
  if (docs.length > 0) groups.push({ title: group.title, docs });
}

/** Sidebar groups, in curated order, with only resolved docs. */
export const docGroups: DocGroup[] = groups;

/** Flat, ordered list of every resolved doc (drives prev/next). */
export const docList: DocEntry[] = groups.flatMap((g) => g.docs);

/** Look up a doc by slug. */
export function getDoc(slug: string): DocEntry | undefined {
  return docList.find((d) => d.slug === slug);
}

/** Prev/next neighbours in reading order for a given slug. */
export function getNeighbors(slug: string): {
  prev: DocEntry | undefined;
  next: DocEntry | undefined;
} {
  const idx = docList.findIndex((d) => d.slug === slug);
  if (idx === -1) return { prev: undefined, next: undefined };
  return {
    prev: idx > 0 ? docList[idx - 1] : undefined,
    next: idx < docList.length - 1 ? docList[idx + 1] : undefined,
  };
}

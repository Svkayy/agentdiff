import { useEffect, useMemo, useRef } from "react";
import { Marked } from "marked";
import DOMPurify from "dompurify";
import { ArrowLeft, ArrowRight, BookOpen } from "lucide-react";
import { docGroups, docList, getDoc, getNeighbors } from "../docs/registry";
import type { DocEntry } from "../docs/registry";

// A single Marked instance. `headerIds` + a slugger give every heading a
// stable id so in-page anchors (#/docs/<slug>#section) resolve, and so the
// on-page "On this page" rail can link into the prose.
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
}

/**
 * Walk a marked inline-token tree and concatenate plain text content,
 * unwrapping formatting (code spans, emphasis, strong, links, etc.) so the
 * result has no raw markdown syntax in it — unlike `token.text` on a heading
 * token, which is the raw markdown source and still contains backticks/
 * asterisks for any inline formatting.
 */
function inlineTokensToPlainText(tokens: unknown[]): string {
  return tokens
    .map((t) => {
      const tok = t as { tokens?: unknown[]; text?: string };
      if (Array.isArray(tok.tokens)) return inlineTokensToPlainText(tok.tokens);
      return tok.text ?? "";
    })
    .join("");
}

interface Heading {
  id: string;
  text: string;
  level: number;
}

/** Render markdown → sanitized HTML, collecting h2/h3 headings for the rail. */
function renderMarkdown(
  markdown: string,
  slug: string,
): { html: string; headings: Heading[] } {
  const headings: Heading[] = [];
  const seen = new Map<string, number>();
  const marked = new Marked({ gfm: true, breaks: false });

  marked.use({
    renderer: {
      heading(
        this: { parser: { parseInline(tokens: unknown[]): string } },
        token: { tokens: unknown[]; depth: number; text: string },
      ) {
        // Plain-text label (backtick-free) drives the id slug and the
        // "On this page" rail text. `token.text` is the raw markdown source
        // of the heading (still containing backticks/asterisks for any
        // inline formatting), so walk the inline token tree instead to get
        // real plain text. The rendered HTML uses marked's own inline parser
        // (matching its default renderer) so inline markdown in the heading
        // — `code`, *emphasis*, links — renders properly instead of showing
        // up as literal source characters.
        const plain = inlineTokensToPlainText(token.tokens);
        const inlineHtml = this.parser.parseInline(token.tokens);
        let id = slugify(plain);
        const n = seen.get(id) ?? 0;
        seen.set(id, n + 1);
        if (n > 0) id = `${id}-${n}`;
        if (token.depth === 2 || token.depth === 3) {
          headings.push({ id, text: plain, level: token.depth });
        }
        // Anchor carries the full route (`#/docs/<slug>#<id>`) so clicking it
        // stays on the doc instead of falling through to the hash router's
        // "no path segment" → Home default.
        return `<h${token.depth} id="${id}"><a class="doc-anchor" href="#/docs/${slug}#${id}" aria-label="Link to this section">#</a>${inlineHtml}</h${token.depth}>`;
      },
    },
  });

  const rawHtml = marked.parse(markdown, { async: false }) as string;
  const html = DOMPurify.sanitize(rawHtml, {
    ADD_ATTR: ["id", "target", "rel"],
  });
  return { html, headings };
}

/** Left sidebar: curated groups → doc links, active slug highlighted. */
function Sidebar({ activeSlug }: { activeSlug: string | null }) {
  return (
    <nav
      aria-label="Docs"
      className="w-full shrink-0 border-b border-hairline pb-6 lg:w-60 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-6"
    >
      <ul className="space-y-6">
        {docGroups.map((group) => (
          <li key={group.title}>
            <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-faint">
              {group.title}
            </p>
            <ul className="space-y-0.5">
              {group.docs.map((doc) => {
                const active = doc.slug === activeSlug;
                return (
                  <li key={doc.slug}>
                    <a
                      href={`#/docs/${doc.slug}`}
                      aria-current={active ? "page" : undefined}
                      className={
                        "block rounded-sm px-2 py-1 text-sm transition-colors duration-200 " +
                        (active
                          ? "bg-card font-medium text-ink shadow-[inset_2px_0_0_0_#15181D]"
                          : "text-muted hover:text-ink")
                      }
                    >
                      {doc.title}
                    </a>
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** In-page "On this page" rail (desktop only). */
function OnThisPage({ slug, headings }: { slug: string; headings: Heading[] }) {
  if (headings.length < 2) return null;
  return (
    <aside className="hidden w-48 shrink-0 xl:block">
      <div className="sticky top-20">
        <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-faint">
          On this page
        </p>
        <ul className="space-y-1 border-l border-hairline">
          {headings.map((h) => (
            <li key={h.id}>
              <a
                href={`#/docs/${slug}#${h.id}`}
                className={
                  "block border-l border-transparent py-0.5 text-sm text-muted transition-colors duration-200 hover:text-ink " +
                  (h.level === 3 ? "pl-6" : "pl-3")
                }
              >
                {h.text}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

/** Prev/next reading-order links at the foot of a doc. */
function PrevNext({ slug }: { slug: string }) {
  const { prev, next } = getNeighbors(slug);
  if (!prev && !next) return null;
  return (
    <nav
      aria-label="Pagination"
      className="mt-12 grid gap-4 border-t border-hairline pt-6 sm:grid-cols-2"
    >
      {prev ? (
        <a
          href={`#/docs/${prev.slug}`}
          className="group flex flex-col rounded-md border border-hairline bg-card p-4 transition-colors duration-200 hover:border-faint"
        >
          <span className="inline-flex items-center gap-1 font-mono text-[11px] uppercase tracking-[0.12em] text-faint">
            <ArrowLeft className="h-3 w-3" aria-hidden="true" /> Previous
          </span>
          <span className="mt-1 text-sm font-medium text-ink">{prev.title}</span>
        </a>
      ) : (
        <span />
      )}
      {next ? (
        <a
          href={`#/docs/${next.slug}`}
          className="group flex flex-col items-end rounded-md border border-hairline bg-card p-4 text-right transition-colors duration-200 hover:border-faint"
        >
          <span className="inline-flex items-center gap-1 font-mono text-[11px] uppercase tracking-[0.12em] text-faint">
            Next <ArrowRight className="h-3 w-3" aria-hidden="true" />
          </span>
          <span className="mt-1 text-sm font-medium text-ink">{next.title}</span>
        </a>
      ) : (
        <span />
      )}
    </nav>
  );
}

/** Docs index — shown at #/docs with no slug. */
function DocsIndex() {
  return (
    <div>
      <p className="font-mono text-[12px] uppercase tracking-[0.16em] text-muted">
        Documentation
      </p>
      <h1 className="mt-3 font-display text-3xl font-extrabold tracking-tight text-ink">
        AgentDiff docs
      </h1>
      <p className="mt-3 max-w-2xl text-lg leading-relaxed text-muted">
        Everything to install AgentDiff, read a behavioral diff, wire the CI gate,
        and run the hosted platform.
      </p>
      <div className="mt-8 space-y-8">
        {docGroups.map((group) => (
          <section key={group.title}>
            <h2 className="font-display text-lg font-bold text-ink">{group.title}</h2>
            <ul className="mt-3 grid gap-3 sm:grid-cols-2">
              {group.docs.map((doc) => (
                <li key={doc.slug}>
                  <a
                    href={`#/docs/${doc.slug}`}
                    className="flex items-start gap-3 rounded-md border border-hairline bg-card p-4 transition-colors duration-200 hover:border-faint"
                  >
                    <BookOpen
                      className="mt-0.5 h-4 w-4 shrink-0 text-faint"
                      aria-hidden="true"
                    />
                    <span className="text-sm font-medium text-ink">{doc.title}</span>
                  </a>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}

/** A single rendered doc. */
function DocArticle({ doc }: { doc: DocEntry }) {
  const { html, headings } = useMemo(
    () => renderMarkdown(doc.markdown, doc.slug),
    [doc.markdown, doc.slug],
  );

  return (
    <div className="flex gap-10">
      <article className="min-w-0 flex-1">
        <p className="font-mono text-[12px] uppercase tracking-[0.16em] text-muted">
          {doc.group}
        </p>
        <div
          className="doc-prose mt-4"
          // Sanitized by DOMPurify above.
          dangerouslySetInnerHTML={{ __html: html }}
        />
        <PrevNext slug={doc.slug} />
      </article>
      <OnThisPage slug={doc.slug} headings={headings} />
    </div>
  );
}

interface DocsPageProps {
  /** null → docs index; otherwise a doc slug. */
  slug: string | null;
}

export function DocsPage({ slug }: DocsPageProps) {
  const notFoundRef = useRef(false);
  const doc = slug ? getDoc(slug) : undefined;
  notFoundRef.current = Boolean(slug) && !doc;

  // Scroll to top on doc change; if the URL carried an in-page anchor, honor it.
  useEffect(() => {
    const anchor = window.location.hash.split("#").slice(2).join("#");
    if (anchor) {
      const el = document.getElementById(anchor);
      if (el) {
        el.scrollIntoView({ behavior: "auto", block: "start" });
        return;
      }
    }
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [slug]);

  return (
    <div className="mx-auto max-w-content px-5 py-10">
      <div className="flex flex-col gap-8 lg:flex-row">
        <Sidebar activeSlug={doc?.slug ?? null} />
        <div className="min-w-0 flex-1">
          {slug === null ? (
            <DocsIndex />
          ) : doc ? (
            <DocArticle doc={doc} />
          ) : (
            <div>
              <h1 className="font-display text-2xl font-bold text-ink">
                Doc not found
              </h1>
              <p className="mt-3 text-muted">
                That page doesn&rsquo;t exist yet.{" "}
                <a className="text-ink underline" href="#/docs">
                  Back to docs
                </a>
                .
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export { docList };

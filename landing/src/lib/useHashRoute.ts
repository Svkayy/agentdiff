import { useEffect, useState } from "react";

/**
 * Minimal hash-based route reader. We use hash routing (not history/pathname)
 * so the single-file GH-Pages bundle is path-free: every route resolves from
 * `index.html` with no server rewrites. Routes:
 *   #/                → home (marketing)
 *   #/docs            → docs index
 *   #/docs/<slug>     → a single doc
 *   #/privacy         → privacy policy (docs shell, slug "privacy")
 *   #/terms           → terms (docs shell, slug "terms")
 *
 * Returns the normalized hash path WITHOUT the leading "#", always starting
 * with "/". A bare "" or "#" normalizes to "/".
 */
export function useHashRoute(): string {
  const [route, setRoute] = useState(() => normalize(window.location.hash));

  useEffect(() => {
    const onHashChange = () => setRoute(normalize(window.location.hash));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return route;
}

function normalize(hash: string): string {
  // Strip a single leading "#". Routes look like "#/docs/<slug>#<heading-id>"
  // when an in-page anchor is appended, so drop everything from the SECOND
  // "#" onward (the route path never contains a literal "#") before deriving
  // the path segment we route on. The in-page anchor itself is read directly
  // from window.location.hash by the scroll effect in DocsPage.
  let h = hash.replace(/^#/, "");
  const anchorIdx = h.indexOf("#");
  if (anchorIdx !== -1) h = h.slice(0, anchorIdx);
  if (h === "" || h === "/") return "/";
  if (!h.startsWith("/")) h = "/" + h;
  return h;
}

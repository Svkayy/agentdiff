// Optional privacy-friendly analytics (Plausible).
//
// Only active when VITE_PLAUSIBLE_DOMAIN is set at build time. When unset,
// this module does nothing and Vite tree-shakes the branch away, so the
// default single-file build ships with zero analytics and no external calls.
//
// Note: the Plausible script is loaded from plausible.io (external host). The
// single-file bundle inlines app assets, but this deliberately stays a runtime
// <script> tag so analytics can be toggled per-deploy without rebuilding the app.
const domain = import.meta.env.VITE_PLAUSIBLE_DOMAIN as string | undefined;

if (domain) {
  const s = document.createElement("script");
  s.defer = true;
  s.setAttribute("data-domain", domain);
  // Hash-based routing: use the hash-aware script so #/docs pageviews register.
  s.src = "https://plausible.io/js/script.hash.js";
  document.head.appendChild(s);
}

export {};

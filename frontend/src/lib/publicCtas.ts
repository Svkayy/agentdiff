export const IS_GITHUB_PAGES_PREVIEW =
  import.meta.env.BASE_URL.replace(/\/$/, "") === "/agentdiff";

export const PUBLIC_DASHBOARD_CTA = IS_GITHUB_PAGES_PREVIEW
  ? { label: "View Demo", path: "/demo" }
  : { label: "Open Dashboard", path: "/projects" };

export const PUBLIC_SIGN_IN_CTA = IS_GITHUB_PAGES_PREVIEW
  ? null
  : { label: "Sign In", path: "/projects" };

export const PUBLIC_SECONDARY_CTA = IS_GITHUB_PAGES_PREVIEW
  ? { label: "Docs", path: "/docs" }
  : { label: "Open Dashboard", path: "/projects" };

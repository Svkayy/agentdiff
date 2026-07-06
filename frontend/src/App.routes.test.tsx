// Regression test for the dashboard 404: DashboardRoutes used a descendant
// <Routes> under parent routes with no trailing splat, so /projects,
// /projects/:id, and /runs/:id all fell through to the catch-all 404 even
// when signed in. The route table must resolve each URL to its page.
import { describe, it, expect, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

vi.mock("@/components/RequireAuth", () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("@/components/Shell", () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("@/components/Toaster", () => ({ Toaster: () => null }));
vi.mock("@/pages/ProjectsPage", () => ({
  ProjectsPage: () => <div>PROJECTS_PAGE</div>,
}));
vi.mock("@/pages/ProjectPage", () => ({
  ProjectPage: () => <div>PROJECT_DETAIL_PAGE</div>,
}));
vi.mock("@/pages/RunDetailPage", () => ({
  RunDetailPage: () => <div>RUN_DETAIL_PAGE</div>,
}));
vi.mock("@/pages/DemoPage", () => ({
  DemoPage: () => <div>DEMO_PAGE</div>,
}));
vi.mock("@/pages/marketing/MarketingLayout", () => ({
  MarketingLayout: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));
vi.mock("@/pages/marketing/MarketingHome", () => ({
  MarketingHome: () => <div>MARKETING_HOME</div>,
}));
vi.mock("@/pages/marketing/components/DocsPage", () => ({
  DocsPage: () => <div>DOCS_PAGE</div>,
}));

import { AppRoutes } from "./App";

function renderAt(path: string): string {
  return renderToString(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("AppRoutes", () => {
  it("renders the projects list at /projects, not the 404", () => {
    const html = renderAt("/projects");
    expect(html).toContain("PROJECTS_PAGE");
    expect(html).not.toContain("Page not found");
  });

  it("renders the project detail at /projects/:id, not the 404", () => {
    const html = renderAt("/projects/abc123");
    expect(html).toContain("PROJECT_DETAIL_PAGE");
    expect(html).not.toContain("Page not found");
  });

  it("renders the run detail at /runs/:id, not the 404", () => {
    const html = renderAt("/runs/run-42");
    expect(html).toContain("RUN_DETAIL_PAGE");
    expect(html).not.toContain("Page not found");
  });

  it("renders the marketing home at /", () => {
    const html = renderAt("/");
    expect(html).toContain("MARKETING_HOME");
  });

  it("renders the public demo at /demo without auth", () => {
    const html = renderAt("/demo");
    expect(html).toContain("DEMO_PAGE");
    expect(html).not.toContain("Page not found");
  });

  it("renders the 404 for unknown URLs", () => {
    const html = renderAt("/definitely-not-a-route");
    expect(html).toContain("Page not found");
  });
});

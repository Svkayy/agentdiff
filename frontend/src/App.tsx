import { BrowserRouter, Routes, Route, Link, Outlet } from "react-router-dom";
import { Shell } from "@/components/Shell";
import { Toaster } from "@/components/Toaster";
import { RequireAuth } from "@/components/RequireAuth";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { ProjectPage } from "@/pages/ProjectPage";
import { RunDetailPage } from "@/pages/RunDetailPage";
import { MarketingLayout } from "@/pages/marketing/MarketingLayout";
import { MarketingHome } from "@/pages/marketing/MarketingHome";
import { DocsPage } from "@/pages/marketing/components/DocsPage";
import { useParams } from "react-router-dom";

/** /docs/:slug — reads the slug from the route and renders the docs shell. */
function DocDetailRoute() {
  const { slug } = useParams<{ slug: string }>();
  return <DocsPage slug={slug ?? null} />;
}

function NotFoundPage() {
  return (
    <div className="mx-auto w-full max-w-[1240px] px-xl py-2xl">
      <div className="border-2 border-foreground bg-background">
        {/* Header-bar nameplate (DESIGN.md card pattern) */}
        <div className="flex items-center justify-between border-b-2 border-foreground px-5 py-3">
          <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
            error.404
          </span>
          <span className="h-2 w-2 bg-[#ea580c]" aria-hidden="true" />
        </div>
        <div className="px-6 py-2xl text-center">
          <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
            404 Not Found
          </div>
          <h1 className="mb-sm font-mono text-2xl font-bold uppercase tracking-tight text-foreground">
            Page not found
          </h1>
          <p className="mb-lg mx-auto max-w-md font-mono text-small text-muted-foreground">
            The page you&apos;re looking for doesn&apos;t exist or has been moved.
          </p>
          <Link
            to="/projects"
            className="inline-block bg-foreground px-lg py-sm font-mono text-xs uppercase tracking-wider text-background transition-opacity hover:opacity-80"
          >
            Back to Projects
          </Link>
        </div>
      </div>
    </div>
  );
}

/** The Clerk-gated dashboard layout, mounted once under one ClerkProvider.
 *  A layout route (not a descendant <Routes>): the parent routes below have no
 *  trailing splat, so a nested <Routes> would never match and every dashboard
 *  URL would fall through to the 404. Children render via <Outlet>. */
function DashboardLayout() {
  return (
    <RequireAuth>
      <Shell>
        <Outlet />
      </Shell>
    </RequireAuth>
  );
}

/** Route table, exported without a router so tests can mount it in a
 *  MemoryRouter. */
export function AppRoutes() {
  return (
    <Routes>
        {/* ── Public marketing + docs (render without Clerk) ─────────────── */}
        <Route
          path="/"
          element={
            <MarketingLayout>
              <MarketingHome />
            </MarketingLayout>
          }
        />
        <Route
          path="/docs"
          element={
            <MarketingLayout>
              <DocsPage slug={null} />
            </MarketingLayout>
          }
        />
        <Route
          path="/docs/:slug"
          element={
            <MarketingLayout>
              <DocDetailRoute />
            </MarketingLayout>
          }
        />
        <Route
          path="/privacy"
          element={
            <MarketingLayout>
              <DocsPage slug="privacy" />
            </MarketingLayout>
          }
        />
        <Route
          path="/terms"
          element={
            <MarketingLayout>
              <DocsPage slug="terms" />
            </MarketingLayout>
          }
        />

        {/* ── Clerk-gated dashboard ──────────────────────────────────────── */}
        <Route element={<DashboardLayout />}>
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectPage />} />
          <Route path="/runs/:id" element={<RunDetailPage />} />
        </Route>

        {/* ── Global 404 ─────────────────────────────────────────────────── */}
        <Route
          path="*"
          element={
            <MarketingLayout>
              <NotFoundPage />
            </MarketingLayout>
          }
        />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
      <Toaster />
    </BrowserRouter>
  );
}

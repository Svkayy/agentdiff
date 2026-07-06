import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
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
      <div className="rounded-md border border-hairline bg-white p-2xl text-center">
        <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
          404 Not Found
        </div>
        <h1 className="mb-sm font-display text-h1 font-bold text-ink-dark">
          Page not found
        </h1>
        <p className="mb-lg max-w-md mx-auto text-small text-neutral-muted">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <Link
          to="/projects"
          className="rounded-sm bg-ink-dark px-lg py-sm text-small font-medium text-white transition-opacity hover:opacity-80"
        >
          Back to Projects
        </Link>
      </div>
    </div>
  );
}

/** The Clerk-gated dashboard subtree, mounted once under one ClerkProvider. */
function DashboardRoutes() {
  return (
    <RequireAuth>
      <Shell>
        <Routes>
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectPage />} />
          <Route path="/runs/:id" element={<RunDetailPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Shell>
    </RequireAuth>
  );
}

export default function App() {
  return (
    <BrowserRouter>
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
        <Route path="/projects" element={<DashboardRoutes />} />
        <Route path="/projects/:id" element={<DashboardRoutes />} />
        <Route path="/runs/:id" element={<DashboardRoutes />} />
      </Routes>
      <Toaster />
    </BrowserRouter>
  );
}

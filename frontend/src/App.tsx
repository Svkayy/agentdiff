import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { SignedIn, SignedOut, SignIn, useClerk } from "@clerk/clerk-react";
import { Shell } from "@/components/Shell";
import { Toaster } from "@/components/Toaster";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { ProjectPage } from "@/pages/ProjectPage";
import { RunDetailPage } from "@/pages/RunDetailPage";
import { registerSignOut } from "@/lib/auth";

/** Hand Clerk's signOut to lib/auth so a 401 can force a clean sign-out. */
function SignOutBridge() {
  const { signOut } = useClerk();
  useEffect(() => {
    registerSignOut((opts) => signOut(opts));
  }, [signOut]);
  return null;
}

function AuthGate() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-shell-bg">
      <SignIn />
    </div>
  );
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
          to="/"
          className="rounded-sm bg-ink-dark px-lg py-sm text-small font-medium text-white transition-opacity hover:opacity-80"
        >
          Back to Projects
        </Link>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <SignedOut>
        <AuthGate />
      </SignedOut>
      <SignedIn>
        <SignOutBridge />
        <Shell>
          <Routes>
            <Route path="/" element={<ProjectsPage />} />
            <Route path="/projects/:id" element={<ProjectPage />} />
            <Route path="/runs/:id" element={<RunDetailPage />} />
            {/* Catch-all: any unknown path → friendly not-found page */}
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Shell>
      </SignedIn>
      <Toaster />
    </BrowserRouter>
  );
}

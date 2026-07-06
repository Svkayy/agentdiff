import { useEffect, type ReactNode } from "react";
import {
  ClerkProvider,
  SignedIn,
  SignedOut,
  SignIn,
  useClerk,
} from "@clerk/clerk-react";
import { registerSignOut } from "@/lib/auth";

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as
  | string
  | undefined;
const APP_BASE =
  import.meta.env.BASE_URL === "/"
    ? ""
    : import.meta.env.BASE_URL.replace(/\/$/, "");
const DASHBOARD_PATH = `${APP_BASE}/projects`;

/** Shown on gated routes when Clerk is not configured. Marketing routes never
 *  hit this — they render without Clerk entirely. */
function MissingClerkConfig() {
  return (
    <div className="dot-grid-bg flex min-h-screen items-center justify-center bg-background px-6">
      <div className="w-full max-w-[440px] border-2 border-foreground bg-background">
        {/* Header-bar nameplate */}
        <div className="flex items-center justify-between border-b-2 border-foreground px-5 py-3">
          <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
            config.env
          </span>
          <span className="h-2 w-2 bg-[#ea580c]" aria-hidden="true" />
        </div>
        <div className="px-6 py-8">
          <div className="mb-md font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
            Configuration required
          </div>
          <h1 className="mb-md font-mono text-xl font-bold uppercase text-foreground">
            Clerk not configured
          </h1>
          <p className="mb-lg font-mono text-sm leading-relaxed text-muted-foreground">
            Set{" "}
            <code className="border border-border bg-muted px-1.5 py-0.5 font-mono text-foreground">
              VITE_CLERK_PUBLISHABLE_KEY
            </code>{" "}
            in your <code className="font-mono text-foreground">.env</code> file and restart the
            dev server.
          </p>
          <pre className="overflow-x-auto border-2 border-foreground bg-foreground px-3.5 py-3 font-mono text-xs text-background">
            {`VITE_CLERK_PUBLISHABLE_KEY=pk_test_...`}
          </pre>
        </div>
      </div>
    </div>
  );
}

/** Hand Clerk's signOut to lib/auth so a 401 can force a clean sign-out. */
function SignOutBridge() {
  const { signOut } = useClerk();
  useEffect(() => {
    registerSignOut((opts) => signOut(opts));
  }, [signOut]);
  return null;
}

function AuthWall() {
  return (
    <div className="dot-grid-bg flex min-h-screen items-center justify-center bg-background">
      <SignIn />
    </div>
  );
}

/**
 * Route-level auth gate for the dashboard. Wraps its children in ClerkProvider
 * (only mounted here, so marketing routes stay Clerk-free). Unauthenticated
 * visits show the Clerk sign-in wall; a missing publishable key shows the
 * MissingClerkConfig card — but ONLY on gated routes.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  if (!PUBLISHABLE_KEY) {
    return <MissingClerkConfig />;
  }
  return (
    <ClerkProvider
      publishableKey={PUBLISHABLE_KEY}
      signInFallbackRedirectUrl={DASHBOARD_PATH}
      signUpFallbackRedirectUrl={DASHBOARD_PATH}
    >
      <SignedOut>
        <AuthWall />
      </SignedOut>
      <SignedIn>
        <SignOutBridge />
        {children}
      </SignedIn>
    </ClerkProvider>
  );
}

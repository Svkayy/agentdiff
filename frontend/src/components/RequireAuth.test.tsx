// @vitest-environment jsdom
// Auth-gate states: missing publishable key → config card; signed-out →
// Clerk sign-in wall; signed-in → gated children render.
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

// Signed-in/out is toggled per test via this mutable flag.
const clerkState = { signedIn: false };

vi.mock("@clerk/clerk-react", () => ({
  ClerkProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="clerk-provider">{children}</div>
  ),
  SignedIn: ({ children }: { children: React.ReactNode }) =>
    clerkState.signedIn ? <>{children}</> : null,
  SignedOut: ({ children }: { children: React.ReactNode }) =>
    clerkState.signedIn ? null : <>{children}</>,
  SignIn: () => <div>SIGN_IN_WALL</div>,
  useClerk: () => ({ signOut: vi.fn() }),
}));

async function loadRequireAuth(key: string) {
  vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", key);
  vi.resetModules();
  const mod = await import("./RequireAuth");
  return mod.RequireAuth;
}

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

describe("RequireAuth", () => {
  it("shows the Clerk-not-configured card when the publishable key is missing", async () => {
    const RequireAuth = await loadRequireAuth("");
    render(
      <RequireAuth>
        <div>GATED_CONTENT</div>
      </RequireAuth>,
    );
    expect(screen.getByText(/clerk not configured/i)).toBeTruthy();
    expect(screen.queryByText("GATED_CONTENT")).toBeNull();
  });

  it("shows the sign-in wall when signed out", async () => {
    clerkState.signedIn = false;
    const RequireAuth = await loadRequireAuth("pk_test_abc");
    render(
      <RequireAuth>
        <div>GATED_CONTENT</div>
      </RequireAuth>,
    );
    expect(screen.getByText("SIGN_IN_WALL")).toBeTruthy();
    expect(screen.queryByText("GATED_CONTENT")).toBeNull();
  });

  it("renders gated children when signed in", async () => {
    clerkState.signedIn = true;
    const RequireAuth = await loadRequireAuth("pk_test_abc");
    render(
      <RequireAuth>
        <div>GATED_CONTENT</div>
      </RequireAuth>,
    );
    expect(screen.getByText("GATED_CONTENT")).toBeTruthy();
    expect(screen.queryByText("SIGN_IN_WALL")).toBeNull();
  });
});

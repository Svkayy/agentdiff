// Session-expiry handling. `onUnauthorized()` is called by the central
// `handleApiError` in api.ts whenever the API returns 401 — it signs the user
// out of Clerk, redirects to the sign-in screen, and surfaces a toast so the
// expiry isn't silent.

/** Detail payload for the `agentdiff:toast` CustomEvent the <Toaster> listens for. */
export interface ToastDetail {
  id: number;
  message: string;
  variant: "info" | "error";
}

let toastSeq = 0;

/** Fire a toast. Picked up by the <Toaster> mounted in App.tsx. */
export function toast(message: string, variant: "info" | "error" = "info"): void {
  if (typeof window === "undefined") return;
  const detail: ToastDetail = { id: ++toastSeq, message, variant };
  window.dispatchEvent(new CustomEvent<ToastDetail>("agentdiff:toast", { detail }));
}

// Clerk's signOut is injected once from React (it lives on the Clerk instance,
// not importable at module scope). Until wired, onUnauthorized falls back to a
// plain redirect so a 401 is never swallowed.
type SignOut = (opts?: { redirectUrl?: string }) => Promise<void>;
let clerkSignOut: SignOut | null = null;

/** Called once from a React effect to hand `auth.ts` a Clerk signOut fn. */
export function registerSignOut(fn: SignOut): void {
  clerkSignOut = fn;
}

// Guard so a burst of concurrent 401s only triggers one sign-out/redirect.
let handling = false;

/**
 * Handle an expired/invalid session: toast, sign out of Clerk, redirect to the
 * sign-in screen. Idempotent within a single expiry event.
 */
export function onUnauthorized(): void {
  if (handling) return;
  handling = true;
  toast("Session expired — please sign in again", "error");
  const redirectUrl = "/projects";
  if (clerkSignOut) {
    void clerkSignOut({ redirectUrl }).catch(() => {
      if (typeof window !== "undefined") window.location.href = redirectUrl;
    });
  } else if (typeof window !== "undefined") {
    window.location.href = redirectUrl;
  }
}

/** Test-only: reset the one-shot guard between cases. */
export function __resetUnauthorizedGuard(): void {
  handling = false;
}

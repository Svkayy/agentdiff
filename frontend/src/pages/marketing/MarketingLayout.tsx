import type { ReactNode } from "react";
import { Nav } from "./components/Nav";
import { Footer } from "./components/Footer";

/**
 * Public marketing chrome — Nav + Footer wrapper shared by the home, docs, and
 * legal routes. Renders without Clerk (marketing must work with no env vars).
 */
export function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-shell text-ink">
      <Nav />
      {children}
      <Footer />
    </div>
  );
}

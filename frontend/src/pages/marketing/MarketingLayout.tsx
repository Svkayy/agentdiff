import type { ReactNode } from "react";
import { Navbar } from "./components/Navbar";
import { BrutalistFooter } from "./components/BrutalistFooter";

/**
 * Public marketing chrome — brutalist Navbar + Footer wrapper shared by the
 * home, docs, and legal routes. Renders without Clerk (marketing must work
 * with no env vars). The `dot-grid-bg` shell gives the instrument-panel
 * texture behind every public page.
 */
export function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen dot-grid-bg bg-background text-foreground">
      <Navbar />
      {children}
      <BrutalistFooter />
    </div>
  );
}

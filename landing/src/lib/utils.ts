import { clsx, type ClassValue } from "clsx";
import { useState } from "react";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Framer Motion animates via requestAnimationFrame, which browsers freeze
 * while the document is hidden (backgrounded tab, prerender, headless
 * capture) — entrance animations gated on opacity:0 then never resolve,
 * leaving content permanently invisible. Same risk for prefers-reduced-motion
 * users. Skip straight to the final state in either case; `initial={false}`
 * tells Framer Motion to render at `animate` with no transition.
 */
export function useSkipEntrance(): boolean {
  const [skip] = useState(() => {
    if (typeof document === "undefined") return false;
    const reducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    return document.visibilityState === "hidden" || !!reducedMotion;
  });
  return skip;
}

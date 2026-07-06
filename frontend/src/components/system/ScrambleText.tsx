import { useEffect, useRef, useState } from "react";
import { useInView } from "framer-motion";

const SCRAMBLE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./:";

export interface ScrambleTextProps {
  text: string;
  className?: string;
  /** ms between scramble frames (default 30, matches the reference template). */
  frameMs?: number;
}

/**
 * Brutalist "terminal decode" text reveal — ported from the reference
 * template's inline `ScrambleText` (used in about-section.tsx /
 * pricing-section.tsx). Triggers once when scrolled into view, then
 * resolves the string left-to-right through random characters from the
 * template's charset.
 */
export function ScrambleText({ text, className, frameMs = 30 }: ScrambleTextProps) {
  const [display, setDisplay] = useState(text);
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-50px" });

  useEffect(() => {
    if (!inView) return;
    let iteration = 0;
    const interval = setInterval(() => {
      setDisplay(
        text
          .split("")
          .map((char, i) => {
            if (char === " ") return " ";
            if (i < iteration) return text[i];
            return SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)];
          })
          .join(""),
      );
      iteration += 0.5;
      if (iteration >= text.length) {
        setDisplay(text);
        clearInterval(interval);
      }
    }, frameMs);
    return () => clearInterval(interval);
  }, [inView, text, frameMs]);

  return (
    <span ref={ref} className={className}>
      {display}
    </span>
  );
}

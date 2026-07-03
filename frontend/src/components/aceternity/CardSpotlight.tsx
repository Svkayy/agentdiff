/**
 * CardSpotlight — Aceternity UI "card spotlight" pattern, restyled for
 * DESIGN.md: a mouse-following radial *ink wash* (low-alpha white) on the
 * dark instrument surfaces. No color gradients — the wash is neutral so the
 * ember signal keeps its reservation.
 */
import { useRef, useState } from "react";
import type { ReactNode, MouseEvent } from "react";
import { motion, useMotionValue, useMotionTemplate } from "framer-motion";

export function CardSpotlight({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState(false);
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  function onMouseMove(event: MouseEvent<HTMLDivElement>) {
    const bounds = ref.current?.getBoundingClientRect();
    if (!bounds) return;
    mouseX.set(event.clientX - bounds.left);
    mouseY.set(event.clientY - bounds.top);
  }

  const wash = useMotionTemplate`radial-gradient(280px circle at ${mouseX}px ${mouseY}px, rgba(232, 235, 239, 0.045), transparent 70%)`;

  return (
    <div
      ref={ref}
      onMouseMove={onMouseMove}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={`group relative ${className}`}
    >
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-[inherit] transition-opacity duration-[200ms] ease-out"
        style={{ background: wash, opacity: hovered ? 1 : 0 }}
      />
      {children}
    </div>
  );
}

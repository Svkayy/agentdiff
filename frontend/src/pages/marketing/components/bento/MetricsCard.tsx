import { useEffect, useState } from "react";

interface ScrambleNumberProps {
  target: string;
  label: string;
  delay?: number;
}

/** Numeric scramble reveal — ported from the template's `metrics-card.tsx`. */
function ScrambleNumber({ target, label, delay = 0 }: ScrambleNumberProps) {
  const [display, setDisplay] = useState(target.replace(/[0-9]/g, "0"));

  useEffect(() => {
    const timeout = setTimeout(() => {
      let iterations = 0;
      const maxIterations = 20;

      const interval = setInterval(() => {
        if (iterations >= maxIterations) {
          setDisplay(target);
          clearInterval(interval);
          return;
        }

        setDisplay(
          target
            .split("")
            .map((char, i) => {
              if (!/[0-9]/.test(char)) return char;
              if (iterations > maxIterations - 5 && i < iterations - (maxIterations - 5)) return char;
              return String(Math.floor(Math.random() * 10));
            })
            .join(""),
        );
        iterations++;
      }, 50);

      return () => clearInterval(interval);
    }, delay);

    return () => clearTimeout(timeout);
  }, [target, delay]);

  return (
    <div className="flex flex-col gap-1">
      <span
        className="text-3xl lg:text-4xl font-mono font-bold tracking-tight text-foreground"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {display}
      </span>
      <span className="text-[11px] tracking-[0.16em] uppercase text-muted-foreground">{label}</span>
    </div>
  );
}

/**
 * Bento metrics card — ported from the template's `metrics-card.tsx`. All
 * figures are TRUTHFUL product facts, not usage numbers: 8 provider parsers,
 * 4 framework adapters, the 0.05 significance level, and the ~540-test suite.
 */
export function MetricsCard() {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between border-b-2 border-foreground px-4 py-2">
        <span className="text-[11px] tracking-widest text-muted-foreground uppercase">
          product.metrics
        </span>
        <span className="inline-block h-2 w-2 bg-[#ea580c]" />
      </div>
      <div className="grid grid-cols-2 flex-1">
        <div className="flex flex-col justify-center gap-1 p-6 border-r-2 border-b-2 border-foreground">
          <ScrambleNumber target="8" label="Provider Parsers" delay={500} />
        </div>
        <div className="flex flex-col justify-center gap-1 p-6 border-b-2 border-foreground">
          <ScrambleNumber target="4" label="Framework Adapters" delay={800} />
        </div>
        <div className="flex flex-col justify-center gap-1 p-6 border-r-2 border-foreground">
          <ScrambleNumber target="~540" label="Tests Passing" delay={1100} />
        </div>
        <div className="flex flex-col justify-center gap-1 p-6">
          <ScrambleNumber target="0.05" label="Significance a" delay={1400} />
        </div>
      </div>
    </div>
  );
}

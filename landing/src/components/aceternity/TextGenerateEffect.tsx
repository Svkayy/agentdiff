import { motion } from "framer-motion";
import { cn, useSkipEntrance } from "@/lib/utils";

/**
 * Aceternity "Text Generate Effect" pattern, adapted: words fade in once with
 * a short ease-out stagger, no blur filter, no color cycling. After the enter
 * animation the text is still.
 */
export function TextGenerateEffect({
  words,
  className,
  delay = 0,
}: {
  words: string;
  className?: string;
  delay?: number;
}) {
  const skip = useSkipEntrance();
  const tokens = words.split(" ");
  return (
    <motion.p
      className={cn(className)}
      initial={skip ? "visible" : "hidden"}
      animate="visible"
      transition={{ staggerChildren: 0.028, delayChildren: delay }}
    >
      {tokens.map((word, i) => (
        <motion.span
          key={`${word}-${i}`}
          className="inline-block"
          variants={{
            hidden: { opacity: 0, y: 4 },
            visible: {
              opacity: 1,
              y: 0,
              transition: { duration: 0.32, ease: "easeOut" },
            },
          }}
        >
          {word}
          {i < tokens.length - 1 ? " " : ""}
        </motion.span>
      ))}
    </motion.p>
  );
}

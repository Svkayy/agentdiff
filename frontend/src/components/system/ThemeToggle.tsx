import { useEffect, useState } from "react";
import { Sun, Moon } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useTheme } from "./useTheme";

const ease = [0.22, 1, 0.36, 1] as const;

/**
 * Brutalist theme toggle — ported from the reference template's
 * `components/theme-toggle.tsx`, adapted from `next-themes` to the local
 * `useTheme` hook (Vite has no next-themes / SSR hydration step, but we
 * keep the "mounted" placeholder so the icon doesn't flash before the
 * persisted theme is read).
 */
export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <div className="w-8 h-8 border border-foreground/20" aria-hidden="true" />
    );
  }

  const isDark = theme === "dark";

  return (
    <motion.button
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.92 }}
      onClick={toggleTheme}
      className="relative w-8 h-8 flex items-center justify-center border border-foreground/20 bg-background/50 hover:bg-foreground/5 transition-colors duration-200"
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
    >
      <AnimatePresence mode="wait" initial={false}>
        {isDark ? (
          <motion.span
            key="sun"
            initial={{ opacity: 0, rotate: -90, scale: 0.5 }}
            animate={{ opacity: 1, rotate: 0, scale: 1 }}
            exit={{ opacity: 0, rotate: 90, scale: 0.5 }}
            transition={{ duration: 0.25, ease }}
          >
            <Sun size={14} strokeWidth={1.5} />
          </motion.span>
        ) : (
          <motion.span
            key="moon"
            initial={{ opacity: 0, rotate: 90, scale: 0.5 }}
            animate={{ opacity: 1, rotate: 0, scale: 1 }}
            exit={{ opacity: 0, rotate: -90, scale: 0.5 }}
            transition={{ duration: 0.25, ease }}
          >
            <Moon size={14} strokeWidth={1.5} />
          </motion.span>
        )}
      </AnimatePresence>
    </motion.button>
  );
}

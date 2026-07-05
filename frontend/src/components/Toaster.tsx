import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { ToastDetail } from "@/lib/auth";

// Minimal toast host. Listens for the `agentdiff:toast` CustomEvent fired by
// `toast()` in lib/auth.ts (used by session-expiry handling and elsewhere).
// Kept dependency-free per DESIGN.md restraint — hairline border, one signal
// color for errors, no gradients.

interface ActiveToast extends ToastDetail {
  leaving?: boolean;
}

export function Toaster() {
  const [toasts, setToasts] = useState<ActiveToast[]>([]);

  useEffect(() => {
    function onToast(e: Event) {
      const detail = (e as CustomEvent<ToastDetail>).detail;
      setToasts((prev) => [...prev, detail]);
      // Auto-dismiss after 5s.
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== detail.id));
      }, 5000);
    }
    window.addEventListener("agentdiff:toast", onToast);
    return () => window.removeEventListener("agentdiff:toast", onToast);
  }, []);

  return (
    <div className="pointer-events-none fixed bottom-lg right-lg z-[100] flex flex-col gap-sm">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className={
              t.variant === "error"
                ? "pointer-events-auto max-w-sm rounded-md border border-ember/30 bg-white px-md py-sm text-small text-ember shadow-sm"
                : "pointer-events-auto max-w-sm rounded-md border border-hairline bg-white px-md py-sm text-small text-ink-dark shadow-sm"
            }
            role="status"
          >
            {t.message}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

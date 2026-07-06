import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { CliReport } from "./CliReport";
import "../index.css";

// CLI single-file entry: renders ONLY the local report dashboard, consuming the
// CLI-injected `window.__AGENTDIFF__` payload. No router, no Clerk — this bundle
// is vendored into the Python package and served offline by `agentdiff`.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <CliReport />
  </StrictMode>,
);

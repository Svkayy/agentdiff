import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

// ClerkProvider is applied per-route inside App (only the gated dashboard
// subtree), so marketing routes render even without Clerk env vars.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

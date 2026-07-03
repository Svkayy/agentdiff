import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ClerkProvider } from "@clerk/clerk-react";
import App from "./App";
import "./index.css";

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;

function MissingClerkConfig() {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#FAFAF8",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div
        style={{
          maxWidth: 440,
          border: "1px solid #E6E3DD",
          borderRadius: 14,
          background: "#fff",
          padding: "40px 36px",
        }}
      >
        <div
          style={{
            fontFamily: "monospace",
            fontSize: 11,
            textTransform: "uppercase",
            letterSpacing: "0.14em",
            color: "#8A929C",
            marginBottom: 12,
          }}
        >
          Configuration required
        </div>
        <h1
          style={{
            fontWeight: 700,
            fontSize: "1.25rem",
            color: "#15181D",
            margin: "0 0 12px",
          }}
        >
          Clerk not configured
        </h1>
        <p style={{ color: "#5B6470", margin: "0 0 20px", lineHeight: 1.5 }}>
          Set{" "}
          <code
            style={{
              fontFamily: "monospace",
              background: "#F4F2EE",
              borderRadius: 4,
              padding: "2px 6px",
            }}
          >
            VITE_CLERK_PUBLISHABLE_KEY
          </code>{" "}
          in your <code style={{ fontFamily: "monospace" }}>.env</code> file and
          restart the dev server.
        </p>
        <pre
          style={{
            background: "#F4F2EE",
            borderRadius: 6,
            padding: "12px 14px",
            fontSize: 12,
            color: "#15181D",
            overflowX: "auto",
          }}
        >
          {`VITE_CLERK_PUBLISHABLE_KEY=pk_test_...`}
        </pre>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {PUBLISHABLE_KEY ? (
      <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
        <App />
      </ClerkProvider>
    ) : (
      <MissingClerkConfig />
    )}
  </StrictMode>,
);

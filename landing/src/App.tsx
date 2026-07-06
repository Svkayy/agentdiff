import { useEffect } from "react";
import { Nav } from "./components/Nav";
import { Hero } from "./components/Hero";
import { SlackBrief } from "./components/SlackBrief";
import { Features } from "./components/Features";
import { HowItWorks } from "./components/HowItWorks";
import { Integrations } from "./components/Integrations";
import { Footer } from "./components/Footer";
import { DocsPage } from "./components/DocsPage";
import { useHashRoute } from "./lib/useHashRoute";

function Home() {
  return (
    <main>
      <Hero />
      <SlackBrief />
      <Features />
      <HowItWorks />
      <Integrations />
    </main>
  );
}

export default function App() {
  const route = useHashRoute();

  // Route parsing. Legal pages reuse the docs shell via their registry slugs.
  let content: React.ReactNode;
  if (route === "/privacy") {
    content = <DocsPage slug="privacy" />;
  } else if (route === "/terms") {
    content = <DocsPage slug="terms" />;
  } else if (route === "/docs") {
    content = <DocsPage slug={null} />;
  } else if (route.startsWith("/docs/")) {
    const slug = route.slice("/docs/".length).replace(/\/$/, "");
    content = <DocsPage slug={slug || null} />;
  } else {
    content = <Home />;
  }

  // Keep the document title in step with the route for shareability/SEO.
  useEffect(() => {
    const isDocs =
      route.startsWith("/docs") || route === "/privacy" || route === "/terms";
    document.title = isDocs
      ? "Docs · AgentDiff"
      : "AgentDiff — Behavioral CI gate for AI agents";
  }, [route]);

  return (
    <div className="min-h-screen bg-shell text-ink">
      <Nav />
      {content}
      <Footer />
    </div>
  );
}

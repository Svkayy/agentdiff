import { Nav } from "./components/Nav";
import { Hero } from "./components/Hero";
import { SlackBrief } from "./components/SlackBrief";
import { Features } from "./components/Features";
import { HowItWorks } from "./components/HowItWorks";
import { Integrations } from "./components/Integrations";
import { Footer } from "./components/Footer";

export default function App() {
  return (
    <div className="min-h-screen bg-shell text-ink">
      <Nav />
      <main>
        <Hero />
        <SlackBrief />
        <Features />
        <HowItWorks />
        <Integrations />
      </main>
      <Footer />
    </div>
  );
}

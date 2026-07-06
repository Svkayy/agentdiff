import { Hero } from "./components/Hero";
import { SlackBrief } from "./components/SlackBrief";
import { Features } from "./components/Features";
import { HowItWorks } from "./components/HowItWorks";
import { Integrations } from "./components/Integrations";

/** Marketing landing home — the public "/" route. */
export function MarketingHome() {
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

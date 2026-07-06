import { HeroSection } from "./components/HeroSection";
import { FeatureGrid } from "./components/FeatureGrid";
import { AboutSection } from "./components/AboutSection";
import { GlitchMarquee } from "./components/GlitchMarquee";

/** Brutalist marketing landing home — the public "/" route. */
export function MarketingHome() {
  return (
    <main>
      <HeroSection />
      <FeatureGrid />
      <AboutSection />
      <GlitchMarquee />
    </main>
  );
}

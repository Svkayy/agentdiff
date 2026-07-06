/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Hosted dashboard URL for CTAs. Defaults to https://app.agentdiff.ai. */
  readonly VITE_APP_URL?: string;
  /** Plausible analytics domain. When set, analytics is injected at runtime. */
  readonly VITE_PLAUSIBLE_DOMAIN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import * as Tabs from "@radix-ui/react-tabs";
import {
  fetchRuns,
  fetchProjectStats,
  listKeys,
  putSlackConfig,
  getSlackStatus,
  getSlackInstallUrl,
  disconnectSlack,
  mintKey,
  revokeKey,
  type Run,
  type ApiKey,
  type MintedKey,
  type SlackStatus,
  type ProjectStats,
} from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Verdict badge ──────────────────────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: string | null }) {
  const styles: Record<string, string> = {
    pass: "bg-verdict-pass/10 text-verdict-pass border border-verdict-pass/30",
    warn: "bg-verdict-warn/10 text-verdict-warn border border-verdict-warn/30",
    fail: "bg-ember/10 text-ember border border-ember/30",
  };
  const v = verdict ?? "—";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest",
        verdict ? styles[verdict] ?? "border border-hairline text-neutral-faint" : "text-neutral-faint",
      )}
    >
      {v}
    </span>
  );
}

function KindBadge({ kind }: { kind: string }) {
  return kind === "drift" ? (
    <span className="inline-flex items-center rounded-sm border border-ember/30 px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest text-ember">
      Live Drift
    </span>
  ) : (
    <span className="inline-flex items-center rounded-sm border border-hairline px-sm py-2xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
      CI
    </span>
  );
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function StatChip({
  label,
  value,
  ember,
}: {
  label: string;
  value: string;
  ember?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2xs">
      <span className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
        {label}
      </span>
      <span
        className={cn(
          "font-mono text-small font-medium tabular-nums",
          ember ? "text-ember" : "text-ink-dark",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function VerdictDot({
  verdict,
  runId,
  createdAt,
}: {
  verdict: string | null;
  runId: string;
  createdAt: string;
}) {
  const color =
    verdict === "pass"
      ? "bg-verdict-pass"
      : verdict === "warn"
        ? "bg-verdict-warn"
        : verdict === "fail"
          ? "bg-ember"
          : "bg-hairline";
  return (
    <a
      href={`/runs/${runId}`}
      title={`${verdict ?? "—"} · ${new Date(createdAt).toLocaleDateString()}`}
      className={cn(
        "inline-block h-4 w-4 flex-shrink-0 rounded-sm transition-opacity hover:opacity-70",
        color,
      )}
    />
  );
}

function StatsBar({ projectId }: { projectId: string }) {
  const { getToken } = useAuth();
  const [stats, setStats] = useState<ProjectStats | null>(null);

  useEffect(() => {
    fetchProjectStats(projectId, getToken)
      .then(setStats)
      .catch(() => {
        /* hide on error */
      });
  }, [projectId, getToken]);

  if (!stats) {
    // Loading skeleton
    return (
      <div className="mb-xl flex flex-wrap gap-xl">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-10 w-24 animate-pulse rounded-sm border border-hairline bg-hairline" />
        ))}
      </div>
    );
  }

  const passRateStr =
    stats.pass_rate_30 !== null
      ? `${Math.round(stats.pass_rate_30 * 100)}%`
      : "—";

  return (
    <div className="mb-xl space-y-lg">
      {/* Chips row */}
      <div className="flex flex-wrap gap-xl rounded-md border border-hairline bg-white px-lg py-md">
        <StatChip label="Pass rate (30)" value={passRateStr} />
        <StatChip
          label="Failing streak"
          value={stats.failing_streak > 0 ? String(stats.failing_streak) : "0"}
          ember={stats.failing_streak > 0}
        />
        <StatChip
          label="Last failure"
          value={stats.last_failure_at ? relativeTime(stats.last_failure_at) : "—"}
        />
        <StatChip label="Drift alerts 7d" value={String(stats.drift_runs_7d)} />
      </div>

      {/* Verdict strip */}
      {stats.recent.length > 0 && (
        <div className="flex items-center gap-xs">
          <span className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
            Recent
          </span>
          <div className="flex flex-wrap gap-1">
            {[...stats.recent].reverse().map((r) => (
              <VerdictDot
                key={r.id}
                verdict={r.verdict}
                runId={r.id}
                createdAt={r.created_at}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Runs tab ──────────────────────────────────────────────────────────────────

function RunsTab({ projectId }: { projectId: string }) {
  const { getToken } = useAuth();
  const navigate = useNavigate();
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const hasPending = runs.some((r) => r.status === "pending" || r.status === "processing");

  const load = useCallback(async () => {
    try {
      const data = await fetchRuns(projectId, getToken);
      setRuns(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load runs");
    } finally {
      setLoading(false);
    }
  }, [projectId, getToken]);

  useEffect(() => {
    void load();
  }, [load]);

  // Auto-refresh every 15s while any run is pending/processing
  useEffect(() => {
    if (hasPending) {
      intervalRef.current = setInterval(() => void load(), 15_000);
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [hasPending, load]);

  if (loading) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-14 animate-pulse rounded-sm border border-hairline bg-hairline" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-sm border border-ember/30 bg-ember/5 px-md py-sm text-small text-ember">
        {error}
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="rounded-md border border-hairline bg-white py-2xl text-center">
        <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
          No runs yet
        </div>
        <h3 className="mb-sm font-display text-h2 font-bold text-ink-dark">
          No runs yet
        </h3>
        <p className="mx-auto mb-lg max-w-md text-small text-neutral-muted">
          Run the CI gate or start the live collector to see results here.
        </p>
        <pre className="mx-auto inline-block rounded-sm border border-hairline bg-shell-bg px-lg py-md text-left font-mono text-micro text-ink-dark">
          {`agentdiff run --project $PROJECT_ID`}
        </pre>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-hairline bg-white">
      <table className="w-full text-small">
        <thead>
          <tr className="border-b border-hairline">
            <th className="px-md py-sm text-left font-mono text-micro font-medium uppercase tracking-widest text-neutral-faint">
              Verdict
            </th>
            <th className="px-md py-sm text-left font-mono text-micro font-medium uppercase tracking-widest text-neutral-faint">
              Kind
            </th>
            <th className="px-md py-sm text-left font-mono text-micro font-medium uppercase tracking-widest text-neutral-faint">
              Status
            </th>
            <th className="px-md py-sm text-left font-mono text-micro font-medium uppercase tracking-widest text-neutral-faint">
              Refs
            </th>
            <th className="px-md py-sm text-left font-mono text-micro font-medium uppercase tracking-widest text-neutral-faint">
              Created
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr
              key={r.id}
              onClick={() => navigate(`/runs/${r.id}`)}
              className="cursor-pointer border-b border-hairline last:border-0 transition-colors hover:bg-shell-bg"
            >
              <td className="px-md py-sm">
                <VerdictBadge verdict={r.verdict} />
              </td>
              <td className="px-md py-sm">
                <KindBadge kind={r.kind} />
              </td>
              <td className="px-md py-sm font-mono text-micro text-neutral-muted">
                {r.status}
              </td>
              <td className="px-md py-sm font-mono text-micro text-neutral-muted">
                <span className="text-ink-dark">{r.baseline_ref.slice(0, 7)}</span>
                <span className="mx-xs text-neutral-faint">→</span>
                <span className="text-ink-dark">{r.candidate_ref.slice(0, 7)}</span>
              </td>
              <td className="px-md py-sm font-mono text-micro text-neutral-faint">
                {new Date(r.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Setup tab ─────────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    void navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <button
      onClick={copy}
      className="rounded-sm border border-hairline bg-shell-bg px-sm py-2xs font-mono text-micro text-neutral-muted transition-colors hover:border-ink-dark hover:text-ink-dark"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function CodeBlock({ code, label }: { code: string; label: string }) {
  return (
    <div className="rounded-md border border-hairline bg-white">
      <div className="flex items-center justify-between border-b border-hairline px-md py-sm">
        <span className="font-mono text-micro uppercase tracking-widest text-neutral-faint">
          {label}
        </span>
        <CopyButton text={code} />
      </div>
      <pre className="overflow-x-auto px-md py-md font-mono text-micro text-ink-dark">
        {code}
      </pre>
    </div>
  );
}

function RevealKeyModal({ minted, onClose }: { minted: MintedKey; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    void navigator.clipboard.writeText(minted.key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-dark/40 backdrop-blur-sm">
      <div className="mx-4 w-full max-w-md rounded-lg border border-hairline bg-white p-xl shadow-xl">
        <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
          API Key Created
        </div>
        <h2 className="mb-sm font-display text-h2 font-bold text-ink-dark">
          Copy your key now
        </h2>
        <p className="mb-lg text-small text-neutral-muted">
          You won't be able to see this key again after closing this dialog.
        </p>
        <div className="mb-lg flex items-center gap-sm rounded-sm border border-hairline bg-shell-bg px-md py-sm">
          <code className="flex-1 break-all font-mono text-micro text-ink-dark">
            {minted.key}
          </code>
          <button
            onClick={copy}
            className="shrink-0 rounded-sm border border-hairline bg-white px-sm py-2xs font-mono text-micro text-neutral-muted transition-colors hover:border-ink-dark"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
        <div className="mb-lg flex items-start gap-sm rounded-sm border border-verdict-warn/30 bg-verdict-warn/5 px-md py-sm">
          <span className="mt-0.5 text-verdict-warn">⚠</span>
          <p className="text-small text-verdict-warn">
            Store this key securely. It will not be shown again.
          </p>
        </div>
        <button
          onClick={onClose}
          className="w-full rounded-sm bg-ink-dark px-lg py-sm text-small font-medium text-white"
        >
          I've saved my key
        </button>
      </div>
    </div>
  );
}

function SetupTab({ projectId }: { projectId: string }) {
  const { getToken } = useAuth();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [keysLoading, setKeysLoading] = useState(true);
  const [minting, setMinting] = useState(false);
  const [minted, setMinted] = useState<MintedKey | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadKeys() {
    setKeysLoading(true);
    try {
      const data = await listKeys(projectId, getToken);
      setKeys(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load API keys");
    } finally {
      setKeysLoading(false);
    }
  }

  useEffect(() => {
    void loadKeys();
  }, []);

  async function handleMint() {
    setMinting(true);
    setError(null);
    try {
      const result = await mintKey(projectId, getToken);
      setMinted(result);
      void loadKeys();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to mint key");
    } finally {
      setMinting(false);
    }
  }

  async function handleRevoke(keyId: string) {
    setRevoking(keyId);
    setError(null);
    try {
      await revokeKey(keyId, getToken);
      setKeys((prev) =>
        prev.map((k) =>
          k.id === keyId ? { ...k, revoked_at: new Date().toISOString() } : k,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to revoke key");
    } finally {
      setRevoking(null);
      setConfirmRevoke(null);
    }
  }

  const apiUrl = import.meta.env.VITE_AGENTDIFF_API_URL ?? "https://api.agentdiff.ai";

  const ghYaml = `- name: AgentDiff CI
  uses: agentdiff/action@v1
  with:
    project_id: ${projectId}
    api_url: ${apiUrl}
  env:
    AGENTDIFF_API_KEY: \${{ secrets.AGENTDIFF_API_KEY }}`;

  const envSnippet = `AGENTDIFF_API_URL=${apiUrl}
AGENTDIFF_API_KEY=<your-key>`;

  const pipSnippet = `pip install agentdiff`;

  return (
    <div className="space-y-2xl">
      {minted && (
        <RevealKeyModal minted={minted} onClose={() => setMinted(null)} />
      )}

      {/* Confirm revoke dialog */}
      {confirmRevoke && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-dark/40 backdrop-blur-sm">
          <div className="mx-4 w-full max-w-sm rounded-lg border border-hairline bg-white p-xl shadow-xl">
            <h2 className="mb-sm font-display text-h2 font-bold text-ink-dark">
              Revoke API key?
            </h2>
            <p className="mb-lg text-small text-neutral-muted">
              This is irreversible. Any systems using this key will stop working.
            </p>
            <div className="flex gap-md">
              <button
                onClick={() => setConfirmRevoke(null)}
                className="flex-1 rounded-sm border border-hairline px-md py-sm text-small font-medium text-ink-dark"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleRevoke(confirmRevoke)}
                disabled={revoking === confirmRevoke}
                className="flex-1 rounded-sm bg-ink text-white hover:bg-[#2A2E35] px-md py-sm text-small font-medium disabled:opacity-40"
              >
                {revoking === confirmRevoke ? "Revoking…" : "Revoke"}
              </button>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-sm border border-ember/30 bg-ember/5 px-md py-sm text-small text-ember">
          {error}
        </div>
      )}

      {/* API Keys section */}
      <section>
        <div className="mb-lg flex items-center justify-between">
          <div>
            <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
              Authentication
            </div>
            <h2 className="font-display text-h2 font-bold text-ink-dark">API Keys</h2>
          </div>
          <button
            onClick={() => void handleMint()}
            disabled={minting}
            className="rounded-sm bg-ink-dark px-md py-sm text-small font-medium text-white transition-opacity disabled:opacity-40"
          >
            {minting ? "Creating…" : "+ New API key"}
          </button>
        </div>

        {keysLoading ? (
          <div className="h-20 animate-pulse rounded-sm border border-hairline bg-hairline" />
        ) : keys.length === 0 ? (
          <div className="rounded-md border border-hairline bg-white py-lg text-center text-small text-neutral-muted">
            No API keys yet — create one above.
          </div>
        ) : (
          <div className="overflow-hidden rounded-md border border-hairline bg-white">
            <table className="w-full text-small">
              <thead>
                <tr className="border-b border-hairline">
                  <th className="px-md py-sm text-left font-mono text-micro font-medium uppercase tracking-widest text-neutral-faint">
                    Prefix
                  </th>
                  <th className="px-md py-sm text-left font-mono text-micro font-medium uppercase tracking-widest text-neutral-faint">
                    Created
                  </th>
                  <th className="px-md py-sm text-left font-mono text-micro font-medium uppercase tracking-widest text-neutral-faint">
                    Last used
                  </th>
                  <th className="px-md py-sm text-left font-mono text-micro font-medium uppercase tracking-widest text-neutral-faint">
                    Status
                  </th>
                  <th className="px-md py-sm" />
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr
                    key={k.id}
                    className="border-b border-hairline last:border-0"
                  >
                    <td className="px-md py-sm font-mono text-micro text-ink-dark">
                      {k.prefix}…
                    </td>
                    <td className="px-md py-sm font-mono text-micro text-neutral-faint">
                      {new Date(k.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-md py-sm font-mono text-micro text-neutral-faint">
                      {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-md py-sm">
                      {k.revoked_at ? (
                        <span className="font-mono text-micro text-muted line-through">Revoked</span>
                      ) : (
                        <span className="font-mono text-micro text-verdict-pass">Active</span>
                      )}
                    </td>
                    <td className="px-md py-sm text-right">
                      {!k.revoked_at && (
                        <button
                          onClick={() => setConfirmRevoke(k.id)}
                          className="text-micro text-neutral-faint transition-colors hover:text-ember"
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Installation snippets */}
      <section>
        <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
          Install
        </div>
        <h2 className="mb-lg font-display text-h2 font-bold text-ink-dark">
          Quick start
        </h2>
        <div className="space-y-md">
          <CodeBlock label="pip install" code={pipSnippet} />
          <CodeBlock label=".env" code={envSnippet} />
          <CodeBlock label="GitHub Action (steps:)" code={ghYaml} />
        </div>
      </section>
    </div>
  );
}

// ── Slack tab ─────────────────────────────────────────────────────────────────

function SlackTab({ projectId }: { projectId: string }) {
  const { getToken } = useAuth();

  // OAuth status
  const [status, setStatus] = useState<SlackStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  // Banners from callback redirect param
  const [oauthBanner, setOauthBanner] = useState<"connected" | "error" | null>(null);

  // Install flow
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);

  // Disconnect flow
  const [disconnecting, setDisconnecting] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);

  // Manual form (advanced)
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [channelId, setChannelId] = useState("");
  const [botToken, setBotToken] = useState("");
  const [saving, setSaving] = useState(false);
  const [manualSuccess, setManualSuccess] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);

  // On mount: read ?slack=connected|error from URL, then strip it.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const slackParam = params.get("slack");
    if (slackParam === "connected" || slackParam === "error") {
      setOauthBanner(slackParam as "connected" | "error");
      params.delete("slack");
      const newSearch = params.toString();
      const newUrl =
        window.location.pathname + (newSearch ? `?${newSearch}` : "") + window.location.hash;
      history.replaceState(null, "", newUrl);
    }
  }, []);

  const loadStatus = async () => {
    setStatusLoading(true);
    try {
      const s = await getSlackStatus(projectId, getToken);
      setStatus(s);
    } catch {
      setStatus(null);
    } finally {
      setStatusLoading(false);
    }
  };

  useEffect(() => {
    void loadStatus();
  }, [projectId]);

  async function handleAddToSlack() {
    setInstalling(true);
    setInstallError(null);
    try {
      const { url } = await getSlackInstallUrl(projectId, getToken);
      window.location.href = url;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed";
      if (msg.includes("503")) {
        setInstallError(
          "Slack OAuth isn't configured on this server — use manual setup below.",
        );
        setAdvancedOpen(true);
      } else {
        setInstallError(msg);
      }
      setInstalling(false);
    }
  }

  async function handleDisconnect() {
    setDisconnecting(true);
    try {
      await disconnectSlack(projectId, getToken);
      setConfirmDisconnect(false);
      await loadStatus();
    } catch {
      // swallow — idempotent
    } finally {
      setDisconnecting(false);
    }
  }

  async function handleManualSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setManualError(null);
    setManualSuccess(false);
    try {
      await putSlackConfig(projectId, channelId, botToken, getToken);
      setManualSuccess(true);
      await loadStatus();
    } catch (e) {
      setManualError(e instanceof Error ? e.message : "Failed to save Slack config");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-lg space-y-lg">
      {/* Header */}
      <div>
        <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
          Notifications
        </div>
        <h2 className="font-display text-h2 font-bold text-ink-dark">Slack alerts</h2>
        <p className="mt-sm text-small text-neutral-muted">
          AgentDiff posts a verdict card to your Slack channel whenever a CI run
          completes or a live drift anomaly is detected.
        </p>
      </div>

      {/* Banners from OAuth redirect */}
      {oauthBanner === "connected" && (
        <div className="rounded-sm border border-verdict-pass/30 bg-verdict-pass/5 px-md py-sm text-small text-verdict-pass">
          Slack connected successfully.
        </div>
      )}
      {oauthBanner === "error" && (
        <div className="rounded-sm border border-ember/30 bg-ember/5 px-md py-sm text-small text-ember">
          Slack connection failed. Please try again.
        </div>
      )}

      {/* Status card */}
      <div className="rounded-md border border-hairline bg-white p-lg">
        {statusLoading ? (
          <div className="h-10 animate-pulse rounded-sm border border-hairline bg-hairline" />
        ) : status?.connected ? (
          <div className="flex items-center justify-between gap-md">
            <div>
              <div className="mb-2xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
                Connected
              </div>
              <div className="flex items-center gap-sm">
                <span className="font-mono text-small text-ink-dark">
                  {status.channel_id ?? "—"}
                </span>
                <span
                  className={cn(
                    "inline-flex items-center rounded-sm border px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest",
                    status.via === "oauth"
                      ? "border-verdict-pass/30 text-verdict-pass"
                      : "border-hairline text-neutral-faint",
                  )}
                >
                  {status.via ?? "—"}
                </span>
              </div>
            </div>
            {!confirmDisconnect ? (
              <button
                onClick={() => setConfirmDisconnect(true)}
                className="rounded-sm border border-hairline px-md py-sm text-small font-medium text-neutral-muted transition-colors hover:border-ember hover:text-ember"
              >
                Disconnect
              </button>
            ) : (
              <div className="flex items-center gap-sm">
                <span className="text-small text-neutral-muted">Confirm?</span>
                <button
                  onClick={() => setConfirmDisconnect(false)}
                  className="rounded-sm border border-hairline px-sm py-2xs text-small text-ink-dark"
                >
                  Cancel
                </button>
                <button
                  onClick={() => void handleDisconnect()}
                  disabled={disconnecting}
                  className="rounded-sm bg-ember px-sm py-2xs text-small font-medium text-white disabled:opacity-40"
                >
                  {disconnecting ? "Removing…" : "Remove"}
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-md">
            <p className="text-small text-neutral-muted">
              Click <strong>Add to Slack</strong> to connect your workspace. You'll pick a
              channel in Slack's native consent screen — no manual token setup required.
            </p>
            {installError && (
              <div className="rounded-sm border border-ember/30 bg-ember/5 px-md py-sm text-small text-ember">
                {installError}
              </div>
            )}
            <button
              onClick={() => void handleAddToSlack()}
              disabled={installing}
              className="rounded-sm bg-ink-dark px-lg py-sm text-small font-medium text-white transition-opacity disabled:opacity-40"
            >
              {installing ? "Redirecting…" : "Add to Slack"}
            </button>
          </div>
        )}
      </div>

      {/* Advanced: manual setup disclosure */}
      <div>
        <button
          onClick={() => setAdvancedOpen((v) => !v)}
          className="flex items-center gap-xs font-mono text-micro uppercase tracking-widest text-neutral-faint transition-colors hover:text-neutral-muted"
        >
          <span>{advancedOpen ? "▾" : "▸"}</span>
          Advanced: manual setup
        </button>

        {advancedOpen && (
          <div className="mt-md space-y-md">
            <div className="rounded-md border border-hairline bg-white p-lg text-small text-neutral-muted">
              <p className="mb-sm font-medium text-ink-dark">How to create the Slack app:</p>
              <ol className="list-inside list-decimal space-y-xs text-small">
                <li>Go to api.slack.com/apps → Create New App → From scratch</li>
                <li>
                  OAuth &amp; Permissions → Add Bot Token Scope:{" "}
                  <code className="font-mono">chat:write</code>
                </li>
                <li>Install to workspace → copy the Bot User OAuth Token</li>
                <li>
                  Invite the bot to your channel:{" "}
                  <code className="font-mono">/invite @your-bot</code>
                </li>
                <li>Copy the channel ID from the channel URL or right-click menu</li>
              </ol>
            </div>

            {manualSuccess && (
              <div className="rounded-sm border border-verdict-pass/30 bg-verdict-pass/5 px-md py-sm text-small text-verdict-pass">
                Slack configuration saved.
              </div>
            )}

            {manualError && (
              <div className="rounded-sm border border-ember/30 bg-ember/5 px-md py-sm text-small text-ember">
                {manualError}
              </div>
            )}

            <form onSubmit={(e) => void handleManualSubmit(e)} className="space-y-md">
              <div>
                <label className="mb-xs block font-mono text-micro uppercase tracking-widest text-neutral-faint">
                  Channel ID
                </label>
                <input
                  value={channelId}
                  onChange={(e) => setChannelId(e.target.value)}
                  placeholder="C0123ABC456"
                  className="w-full rounded-sm border border-hairline bg-shell-bg px-md py-sm text-small text-ink-dark placeholder:text-neutral-faint focus:border-ink-dark focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-xs block font-mono text-micro uppercase tracking-widest text-neutral-faint">
                  Bot token
                </label>
                <input
                  type="password"
                  value={botToken}
                  onChange={(e) => setBotToken(e.target.value)}
                  placeholder="xoxb-…"
                  className="w-full rounded-sm border border-hairline bg-shell-bg px-md py-sm text-small text-ink-dark placeholder:text-neutral-faint focus:border-ink-dark focus:outline-none"
                />
              </div>
              <button
                type="submit"
                disabled={saving || !channelId.trim() || !botToken.trim()}
                className="rounded-sm bg-ink-dark px-lg py-sm text-small font-medium text-white transition-opacity disabled:opacity-40"
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}

// ── ProjectPage ───────────────────────────────────────────────────────────────

export function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = id ?? "";
  const [tab, setTab] = useState("runs");

  return (
    <div className="mx-auto w-full max-w-[1240px] px-xl py-2xl">
      {/* Breadcrumb */}
      <div className="mb-xl flex items-center gap-xs font-mono text-micro text-neutral-faint">
        <Link to="/" className="transition-colors hover:text-ink-dark">
          Projects
        </Link>
        <span>/</span>
        <span className="text-ink-dark">{projectId.slice(0, 8)}…</span>
      </div>

      <h1 className="mb-2xl font-display text-h1 font-bold text-ink-dark">Project</h1>

      <Tabs.Root value={tab} onValueChange={setTab}>
        <Tabs.List className="mb-xl flex gap-xs border-b border-hairline">
          {(["runs", "setup", "slack"] as const).map((t) => (
            <Tabs.Trigger
              key={t}
              value={t}
              className={cn(
                "border-b-2 px-md pb-sm pt-2xs font-mono text-micro uppercase tracking-widest transition-colors",
                tab === t
                  ? "border-ink-dark text-ink-dark"
                  : "border-transparent text-neutral-faint hover:text-neutral-muted",
              )}
            >
              {t === "runs" ? "Runs" : t === "setup" ? "Setup" : "Slack"}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <Tabs.Content value="runs">
          <StatsBar projectId={projectId} />
          <RunsTab projectId={projectId} />
        </Tabs.Content>
        <Tabs.Content value="setup">
          <SetupTab projectId={projectId} />
        </Tabs.Content>
        <Tabs.Content value="slack">
          <SlackTab projectId={projectId} />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}

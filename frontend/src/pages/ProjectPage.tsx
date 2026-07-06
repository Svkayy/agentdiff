import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import * as Tabs from "@radix-ui/react-tabs";
import {
  fetchRunsPage,
  fetchProjectStats,
  fetchProjects,
  fetchUsage,
  fetchAudit,
  listKeys,
  putSlackConfig,
  getSlackStatus,
  getSlackInstallUrl,
  disconnectSlack,
  mintKey,
  revokeKey,
  renameProject,
  deleteProject,
  deleteRun,
  ApiError,
  type Run,
  type ApiKey,
  type MintedKey,
  type SlackStatus,
  type ProjectStats,
  type Usage,
  type AuditEntry,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "@/lib/auth";

const RUNS_PAGE_SIZE = 20;
const AUDIT_PAGE_SIZE = 20;

const VERDICT_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "pass", label: "Stable" },
  { value: "warn", label: "Notice" },
  { value: "fail", label: "Change" },
];

// ── Verdict badge ──────────────────────────────────────────────────────────────

/** Maps engine verdict values (pass/warn/fail) to user-facing monitoring labels. */
export function verdictLabel(verdict: string | null): string {
  if (verdict === "pass") return "STABLE";
  if (verdict === "warn") return "NOTICE";
  if (verdict === "fail") return "CHANGE";
  return verdict ?? "—";
}

// Verdict mapping (DESIGN.md, locked): pass = neutral/foreground chip;
// warn = orange OUTLINE (border only, no fill); fail = solid #ea580c.
function VerdictBadge({ verdict }: { verdict: string | null }) {
  const styles: Record<string, string> = {
    pass: "border-2 border-foreground text-foreground",
    warn: "border-2 border-[#ea580c] text-[#ea580c]",
    fail: "border-2 border-[#ea580c] bg-[#ea580c] text-background",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest",
        verdict ? styles[verdict] ?? "border-2 border-border text-muted-foreground" : "text-muted-foreground",
      )}
      title={verdict ?? undefined}
    >
      {verdictLabel(verdict)}
    </span>
  );
}

function KindBadge({ kind }: { kind: string }) {
  return kind === "drift" ? (
    <span className="inline-flex items-center border-2 border-[#ea580c] px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest text-[#ea580c]">
      Live Drift
    </span>
  ) : (
    <span className="inline-flex items-center border-2 border-border px-sm py-2xs font-mono text-micro uppercase tracking-widest text-muted-foreground">
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
    <div className="flex flex-col gap-1 border-2 border-foreground px-4 py-3">
      <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </span>
      <span
        className={cn(
          "font-mono text-small font-bold tabular-nums",
          ember ? "text-[#ea580c]" : "text-foreground",
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
  // Verdict mapping (locked): pass = solid foreground; warn = orange outline;
  // fail = solid orange. Kept as distinct fills/borders so the strip stays
  // readable at a glance and without color vision.
  const style =
    verdict === "pass"
      ? "bg-foreground"
      : verdict === "warn"
        ? "border-2 border-[#ea580c] bg-transparent"
        : verdict === "fail"
          ? "bg-[#ea580c]"
          : "border-2 border-border bg-transparent";
  return (
    <a
      href={`/runs/${runId}`}
      title={`${verdictLabel(verdict)} · ${new Date(createdAt).toLocaleDateString()}`}
      className={cn(
        "inline-block h-4 w-4 flex-shrink-0 transition-opacity hover:opacity-70",
        style,
      )}
    />
  );
}

function StatsBar({ projectId }: { projectId: string }) {
  const { getToken } = useAuth();
  const [stats, setStats] = useState<ProjectStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(() => {
    fetchProjectStats(projectId, getToken)
      .then((s) => {
        setStats(s);
        setError(null);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Failed to load stats");
      });
  }, [projectId, getToken]);

  useEffect(() => {
    load();
    intervalRef.current = setInterval(() => void load(), 15_000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [load]);

  // Visible error state with retry — never an infinite skeleton.
  if (!stats && error) {
    return (
      <div className="mb-xl flex items-center justify-between border-2 border-[#ea580c] bg-background px-lg py-md">
        <span className="font-mono text-small text-[#ea580c]">{error}</span>
        <button
          onClick={() => load()}
          className="ml-md border-2 border-[#ea580c] px-md py-2xs font-mono text-small font-medium text-[#ea580c] transition-colors hover:bg-[#ea580c] hover:text-background"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!stats) {
    // Loading skeleton — shown only on first load (stats is null, no error yet)
    return (
      <div className="mb-xl flex flex-wrap gap-md">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-14 w-28 animate-pulse border-2 border-foreground bg-muted" />
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
      <div className="flex flex-wrap gap-md">
        <StatChip label="Pass rate (30)" value={passRateStr} />
        <StatChip
          label="Alert streak"
          value={stats.failing_streak > 0 ? String(stats.failing_streak) : "0"}
          ember={stats.failing_streak > 0}
        />
        <StatChip
          label="Last alert"
          value={stats.last_failure_at ? relativeTime(stats.last_failure_at) : "—"}
        />
        <StatChip label="Drift alerts 7d" value={String(stats.drift_runs_7d)} />
      </div>

      {/* Verdict strip */}
      {stats.recent.length > 0 && (
        <div className="flex items-center gap-xs">
          <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
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
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [verdict, setVerdict] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const hasPending = runs.some((r) => r.status === "pending" || r.status === "processing");

  // Load the first page for the current filters. Debounced against search.
  const loadFirst = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchRunsPage(
        projectId,
        { limit: RUNS_PAGE_SIZE, offset: 0, verdict: verdict || undefined, q: search.trim() || undefined },
        getToken,
      );
      setRuns(data.items);
      setTotal(data.total);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load runs");
    } finally {
      setLoading(false);
    }
  }, [projectId, getToken, verdict, search]);

  // Silent refresh of the currently-loaded rows (used by the poll) — keeps
  // whatever the user has paged in without resetting to page 1.
  const refresh = useCallback(async () => {
    try {
      const data = await fetchRunsPage(
        projectId,
        {
          limit: Math.max(runs.length, RUNS_PAGE_SIZE),
          offset: 0,
          verdict: verdict || undefined,
          q: search.trim() || undefined,
        },
        getToken,
      );
      setRuns(data.items);
      setTotal(data.total);
    } catch {
      /* poll failures are non-fatal */
    }
  }, [projectId, getToken, verdict, search, runs.length]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const data = await fetchRunsPage(
        projectId,
        { limit: RUNS_PAGE_SIZE, offset: runs.length, verdict: verdict || undefined, q: search.trim() || undefined },
        getToken,
      );
      setRuns((prev) => [...prev, ...data.items]);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load more runs");
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleDelete(runId: string) {
    setDeleting(runId);
    try {
      await deleteRun(runId, getToken);
      setRuns((prev) => prev.filter((r) => r.id !== runId));
      setTotal((t) => Math.max(0, t - 1));
      toast("Run deleted");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed to delete run", "error");
    } finally {
      setDeleting(null);
      setConfirmDelete(null);
    }
  }

  // Debounced (re)load whenever filters change.
  useEffect(() => {
    const t = setTimeout(() => void loadFirst(), 250);
    return () => clearTimeout(t);
  }, [loadFirst]);

  // Auto-refresh every 15s while any run is pending/processing
  useEffect(() => {
    if (hasPending) {
      intervalRef.current = setInterval(() => void refresh(), 15_000);
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [hasPending, refresh]);

  const filtersActive = Boolean(search.trim() || verdict);

  // Escape closes the delete-run confirmation modal.
  useEffect(() => {
    if (!confirmDelete) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setConfirmDelete(null);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [confirmDelete]);

  return (
    <div className="space-y-lg">
      {/* Filter bar (bordered segmented) */}
      <div className="flex flex-wrap items-center justify-between gap-md">
        <div className="flex flex-wrap items-center border-2 border-foreground">
          {VERDICT_FILTERS.map((f, i) => (
            <button
              key={f.value || "all"}
              onClick={() => setVerdict(f.value)}
              className={cn(
                "px-md py-sm font-mono text-micro uppercase tracking-widest transition-colors",
                i > 0 && "border-l-2 border-foreground",
                verdict === f.value
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search runs…"
          aria-label="Search runs"
          className="w-56 border-2 border-foreground bg-background px-md py-sm font-mono text-small text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-foreground"
        />
      </div>

      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-14 animate-pulse border-2 border-foreground bg-muted" />
          ))}
        </div>
      ) : error ? (
        <div className="flex items-center justify-between border-2 border-[#ea580c] bg-background px-md py-sm">
          <span className="font-mono text-small text-[#ea580c]">{error}</span>
          <button
            onClick={() => void loadFirst()}
            className="ml-md font-mono text-small font-medium text-[#ea580c] underline"
          >
            Retry
          </button>
        </div>
      ) : runs.length === 0 && filtersActive ? (
        <div className="border-2 border-foreground bg-background py-2xl text-center font-mono text-small text-muted-foreground">
          No runs match your filters.
        </div>
      ) : runs.length === 0 ? (
        <div className="border-2 border-foreground bg-background py-2xl text-center">
          <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
            No runs yet
          </div>
          <h3 className="mb-sm font-mono text-xl font-bold uppercase text-foreground">No runs yet</h3>
          <p className="mx-auto mb-lg max-w-md font-mono text-small text-muted-foreground">
            Run the CI gate or start the live collector to see results here.
          </p>
          <pre className="mx-auto inline-block border-2 border-foreground bg-foreground px-lg py-md text-left font-mono text-micro text-background">
            {`agentdiff run --project $PROJECT_ID`}
          </pre>
        </div>
      ) : (
        <>
          <div className="border-2 border-foreground bg-background">
            <table className="w-full text-small">
              <thead>
                <tr className="border-b-2 border-foreground">
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Verdict
                  </th>
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Kind
                  </th>
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Status
                  </th>
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Refs
                  </th>
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Created
                  </th>
                  <th className="px-md py-sm" />
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => navigate(`/runs/${r.id}`)}
                    className="group cursor-pointer border-b border-border last:border-0 transition-colors hover:bg-foreground/[0.04]"
                  >
                    <td className="px-md py-sm">
                      <VerdictBadge verdict={r.verdict} />
                    </td>
                    <td className="px-md py-sm">
                      <KindBadge kind={r.kind} />
                    </td>
                    <td className="px-md py-sm font-mono text-micro uppercase text-muted-foreground">
                      {r.status}
                    </td>
                    <td className="px-md py-sm font-mono text-micro text-muted-foreground">
                      <span className="text-foreground">{(r.baseline_ref ?? "?").slice(0, 7)}</span>
                      <span className="mx-xs text-muted-foreground">→</span>
                      <span className="text-foreground">{(r.candidate_ref ?? "?").slice(0, 7)}</span>
                    </td>
                    <td className="px-md py-sm font-mono text-micro tabular-nums text-muted-foreground">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="px-md py-sm text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmDelete(r.id);
                        }}
                        className="font-mono text-micro uppercase tracking-wider text-muted-foreground opacity-0 transition-opacity hover:text-[#ea580c] group-hover:opacity-100"
                        aria-label="Delete run"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Load more / count */}
          <div className="flex items-center justify-between">
            <span className="font-mono text-micro tabular-nums text-muted-foreground">
              {runs.length} of {total}
            </span>
            {runs.length < total && (
              <button
                onClick={() => void loadMore()}
                disabled={loadingMore}
                className="border-2 border-foreground bg-background px-lg py-sm font-mono text-xs uppercase tracking-wider text-foreground transition-colors hover:bg-foreground hover:text-background disabled:opacity-40"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            )}
          </div>
        </>
      )}

      {/* Delete run confirmation */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 backdrop-blur-sm">
          <div className="mx-4 w-full max-w-sm border-2 border-foreground bg-background p-xl">
            <h2 className="mb-sm font-mono text-xl font-bold uppercase text-foreground">Delete run?</h2>
            <p className="mb-lg font-mono text-small text-muted-foreground">
              This permanently removes the run and its report. This cannot be undone.
            </p>
            <div className="flex gap-md">
              <button
                onClick={() => setConfirmDelete(null)}
                className="flex-1 border-2 border-foreground px-md py-sm font-mono text-small font-medium uppercase tracking-wider text-foreground transition-colors hover:bg-foreground hover:text-background"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleDelete(confirmDelete)}
                disabled={deleting === confirmDelete}
                className="flex-1 bg-[#ea580c] px-md py-sm font-mono text-small font-medium uppercase tracking-wider text-background disabled:opacity-40"
              >
                {deleting === confirmDelete ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
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
      className="border-2 border-foreground bg-background px-sm py-2xs font-mono text-micro uppercase tracking-wider text-muted-foreground transition-colors hover:bg-foreground hover:text-background"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function CodeBlock({ code, label }: { code: string; label: string }) {
  return (
    <div className="border-2 border-foreground bg-background">
      <div className="flex items-center justify-between border-b-2 border-foreground px-md py-sm">
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          {label}
        </span>
        <CopyButton text={code} />
      </div>
      {/* Terminal-style body: dark plate, cream text */}
      <pre className="overflow-x-auto bg-foreground px-md py-md font-mono text-micro text-background">
        {code}
      </pre>
    </div>
  );
}

function RevealKeyModal({ minted, onClose }: { minted: MintedKey; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  // Copy-first flow: closing requires an explicit "yes I saved it" confirm
  // step, and that step only appears once the key has actually been copied —
  // this is the last time the raw key is ever shown, so we want a
  // deliberate two-step exit rather than a single accidental click.
  const [confirmingClose, setConfirmingClose] = useState(false);

  function copy() {
    void navigator.clipboard.writeText(minted.key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 backdrop-blur-sm">
      <div className="mx-4 w-full max-w-md border-2 border-foreground bg-background p-xl">
        <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          API Key Created
        </div>
        <h2 className="mb-sm font-mono text-xl font-bold uppercase text-foreground">
          Copy your key now
        </h2>
        <p className="mb-lg font-mono text-small text-muted-foreground">
          You won't be able to see this key again after closing this dialog.
        </p>
        <div className="mb-lg flex items-center gap-sm border-2 border-foreground bg-foreground px-md py-sm">
          <code className="flex-1 break-all font-mono text-micro text-background">
            {minted.key}
          </code>
          <button
            onClick={copy}
            aria-label="Copy API key to clipboard"
            className="shrink-0 border-2 border-background bg-foreground px-sm py-2xs font-mono text-micro uppercase tracking-wider text-background transition-colors hover:bg-background hover:text-foreground"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
        <div className="mb-lg flex items-start gap-sm border-2 border-[#ea580c] bg-background px-md py-sm">
          <span className="mt-0.5 text-[#ea580c]">⚠</span>
          <p className="font-mono text-small text-[#ea580c]">
            Store this key securely. It will not be shown again.
          </p>
        </div>

        {!confirmingClose ? (
          <button
            onClick={() => setConfirmingClose(true)}
            className="w-full bg-foreground px-lg py-sm font-mono text-small font-medium uppercase tracking-wider text-background"
          >
            I've saved my key
          </button>
        ) : (
          <div className="space-y-sm border-2 border-foreground bg-background p-md">
            <p className="font-mono text-small font-medium text-foreground">
              Did you save it? This is the only time it will be shown.
            </p>
            <div className="flex gap-sm">
              <button
                onClick={() => setConfirmingClose(false)}
                className="flex-1 border-2 border-foreground bg-background px-lg py-sm font-mono text-small font-medium uppercase tracking-wider text-foreground transition-colors hover:bg-foreground hover:text-background"
              >
                Go back
              </button>
              <button
                onClick={onClose}
                className="flex-1 bg-foreground px-lg py-sm font-mono text-small font-medium uppercase tracking-wider text-background"
              >
                Yes, I saved it
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Usage panel ─────────────────────────────────────────────────────────────

function UsageBar({
  label,
  used,
  limit,
}: {
  label: string;
  used: number;
  limit: number | null;
}) {
  const unlimited = limit === null;
  const pct = unlimited || limit === 0 ? 0 : Math.min(100, Math.round((used / limit) * 100));
  const over = !unlimited && limit > 0 && used >= limit;
  const near = !unlimited && pct >= 80;
  // Verdict-aligned fill: over-limit = solid orange (fail); near = orange
  // outline family isn't available for a solid fill, so use a mid orange amber;
  // normal = solid foreground.
  const barColor = over ? "bg-[#ea580c]" : near ? "bg-[#b45309]" : "bg-foreground";
  return (
    <div>
      <div className="mb-xs flex items-baseline justify-between">
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          {label}
        </span>
        <span className="font-mono text-small tabular-nums text-foreground">
          {used.toLocaleString()}
          <span className="text-muted-foreground">
            {" / "}
            {unlimited ? "∞" : limit.toLocaleString()}
          </span>
        </span>
      </div>
      {/* Throughput-bar: h-2 bordered, solid fill; hatch for unlimited */}
      <div className="h-3 w-full overflow-hidden border-2 border-foreground bg-background">
        {unlimited ? (
          <div className="h-full w-full bg-[repeating-linear-gradient(45deg,hsl(var(--foreground))_0,hsl(var(--foreground))_4px,transparent_4px,transparent_8px)]" />
        ) : (
          <div
            className={cn("h-full transition-all", barColor)}
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
    </div>
  );
}

function UsagePanel() {
  const { getToken } = useAuth();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchUsage(getToken)
      .then((u) => {
        setUsage(u);
        setError(null);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Failed to load usage");
      });
  }, [getToken]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
        Billing
      </div>
      <h2 className="mb-lg font-mono text-xl font-bold uppercase text-foreground">Usage</h2>
      {error ? (
        <div className="flex items-center justify-between border-2 border-[#ea580c] bg-background px-lg py-md">
          <span className="font-mono text-small text-[#ea580c]">{error}</span>
          <button
            onClick={() => load()}
            className="ml-md border-2 border-[#ea580c] px-md py-2xs font-mono text-small font-medium text-[#ea580c] transition-colors hover:bg-[#ea580c] hover:text-background"
          >
            Retry
          </button>
        </div>
      ) : !usage ? (
        <div className="h-28 animate-pulse border-2 border-foreground bg-muted" />
      ) : (
        <div className="border-2 border-foreground bg-background p-lg">
          <div className="mb-lg flex items-center justify-between">
            <span className="inline-flex items-center border-2 border-foreground px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest text-foreground">
              {usage.plan}
            </span>
            <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
              Period {usage.period}
            </span>
          </div>
          <div className="space-y-lg">
            <UsageBar label="Runs" used={usage.runs_used} limit={usage.runs_limit} />
            <UsageBar
              label="Trajectories"
              used={usage.trajectories_used}
              limit={usage.trajectories_limit}
            />
          </div>
        </div>
      )}
    </section>
  );
}

// ── Audit log ───────────────────────────────────────────────────────────────

function AuditPanel({ projectId }: { projectId: string }) {
  const { getToken } = useAuth();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadFirst = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchAudit(projectId, { limit: AUDIT_PAGE_SIZE, offset: 0 }, getToken);
      setEntries(data.items);
      setTotal(data.total);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load audit log");
    } finally {
      setLoading(false);
    }
  }, [projectId, getToken]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const data = await fetchAudit(
        projectId,
        { limit: AUDIT_PAGE_SIZE, offset: entries.length },
        getToken,
      );
      setEntries((prev) => [...prev, ...data.items]);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load more");
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    void loadFirst();
  }, [loadFirst]);

  return (
    <section>
      <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
        Activity
      </div>
      <h2 className="mb-lg font-mono text-xl font-bold uppercase text-foreground">Audit log</h2>
      {loading ? (
        <div className="h-24 animate-pulse border-2 border-foreground bg-muted" />
      ) : error ? (
        <div className="flex items-center justify-between border-2 border-[#ea580c] bg-background px-md py-sm">
          <span className="font-mono text-small text-[#ea580c]">{error}</span>
          <button
            onClick={() => void loadFirst()}
            className="ml-md font-mono text-small font-medium text-[#ea580c] underline"
          >
            Retry
          </button>
        </div>
      ) : entries.length === 0 ? (
        <div className="border-2 border-foreground bg-background py-lg text-center font-mono text-small text-muted-foreground">
          No activity recorded yet.
        </div>
      ) : (
        <>
          <div className="border-2 border-foreground bg-background">
            <table className="w-full text-small">
              <thead>
                <tr className="border-b-2 border-foreground">
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    When
                  </th>
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Actor
                  </th>
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Action
                  </th>
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Target
                  </th>
                </tr>
              </thead>
              <tbody>
                {entries.map((a) => (
                  <tr key={a.id} className="border-b border-border last:border-0">
                    <td className="px-md py-sm font-mono text-micro tabular-nums text-muted-foreground">
                      {new Date(a.created_at).toLocaleString()}
                    </td>
                    <td className="px-md py-sm font-mono text-small text-foreground">{a.actor}</td>
                    <td className="px-md py-sm font-mono text-micro text-foreground">{a.action}</td>
                    <td className="px-md py-sm font-mono text-micro text-muted-foreground">
                      {a.target_type}
                      <span className="text-muted-foreground/70"> · {a.target_id.slice(0, 8)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-md flex items-center justify-between">
            <span className="font-mono text-micro tabular-nums text-muted-foreground">
              {entries.length} of {total}
            </span>
            {entries.length < total && (
              <button
                onClick={() => void loadMore()}
                disabled={loadingMore}
                className="border-2 border-foreground bg-background px-lg py-sm font-mono text-xs uppercase tracking-wider text-foreground transition-colors hover:bg-foreground hover:text-background disabled:opacity-40"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function SetupTab({ projectId }: { projectId: string }) {
  const { getToken } = useAuth();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [keysLoading, setKeysLoading] = useState(true);
  const [minting, setMinting] = useState(false);
  const [minted, setMinted] = useState<MintedKey | null>(null);
  const [namingKey, setNamingKey] = useState(false);
  const [keyName, setKeyName] = useState("");
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
      const result = await mintKey(projectId, keyName.trim() || null, getToken);
      setMinted(result);
      setNamingKey(false);
      setKeyName("");
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 backdrop-blur-sm">
          <div className="mx-4 w-full max-w-sm border-2 border-foreground bg-background p-xl">
            <h2 className="mb-sm font-mono text-xl font-bold uppercase text-foreground">
              Revoke API key?
            </h2>
            <p className="mb-lg font-mono text-small text-muted-foreground">
              This is irreversible. Any systems using this key will stop working.
            </p>
            <div className="flex gap-md">
              <button
                onClick={() => setConfirmRevoke(null)}
                className="flex-1 border-2 border-foreground px-md py-sm font-mono text-small font-medium uppercase tracking-wider text-foreground transition-colors hover:bg-foreground hover:text-background"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleRevoke(confirmRevoke)}
                disabled={revoking === confirmRevoke}
                className="flex-1 bg-[#ea580c] px-md py-sm font-mono text-small font-medium uppercase tracking-wider text-background disabled:opacity-40"
              >
                {revoking === confirmRevoke ? "Revoking…" : "Revoke"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Name-your-key dialog */}
      {namingKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 backdrop-blur-sm">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void handleMint();
            }}
            className="mx-4 w-full max-w-md border-2 border-foreground bg-background p-xl"
          >
            <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
              New API key
            </div>
            <h2 className="mb-sm font-mono text-xl font-bold uppercase text-foreground">Name this key</h2>
            <p className="mb-lg font-mono text-small text-muted-foreground">
              Give the key a label so you can tell it apart later (e.g.{" "}
              <code className="font-mono text-foreground">ci-github</code>). Optional.
            </p>
            <input
              autoFocus
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              placeholder="ci-github"
              className="mb-lg w-full border-2 border-foreground bg-background px-md py-sm font-mono text-small text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-foreground"
            />
            <div className="flex gap-md">
              <button
                type="button"
                onClick={() => setNamingKey(false)}
                className="flex-1 border-2 border-foreground px-md py-sm font-mono text-small font-medium uppercase tracking-wider text-foreground transition-colors hover:bg-foreground hover:text-background"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={minting}
                className="flex-1 bg-foreground px-md py-sm font-mono text-small font-medium uppercase tracking-wider text-background disabled:opacity-40"
              >
                {minting ? "Creating…" : "Create key"}
              </button>
            </div>
          </form>
        </div>
      )}

      {error && (
        <div className="border-2 border-[#ea580c] bg-background px-md py-sm font-mono text-small text-[#ea580c]">
          {error}
        </div>
      )}

      {/* API Keys section */}
      <section>
        <div className="mb-lg flex items-center justify-between">
          <div>
            <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
              Authentication
            </div>
            <h2 className="font-mono text-xl font-bold uppercase text-foreground">API Keys</h2>
          </div>
          <button
            onClick={() => {
              setKeyName("");
              setNamingKey(true);
            }}
            disabled={minting}
            className="bg-foreground px-md py-sm font-mono text-xs uppercase tracking-wider text-background transition-opacity disabled:opacity-40"
          >
            {minting ? "Creating…" : "+ New API key"}
          </button>
        </div>

        {keysLoading ? (
          <div className="h-20 animate-pulse border-2 border-foreground bg-muted" />
        ) : keys.length === 0 ? (
          <div className="border-2 border-foreground bg-background py-lg text-center font-mono text-small text-muted-foreground">
            No API keys yet — create one above.
          </div>
        ) : (
          <div className="border-2 border-foreground bg-background">
            <table className="w-full text-small">
              <thead>
                <tr className="border-b-2 border-foreground">
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Name
                  </th>
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Prefix
                  </th>
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Created
                  </th>
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Last used
                  </th>
                  <th className="px-md py-sm text-left font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    Status
                  </th>
                  <th className="px-md py-sm" />
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr
                    key={k.id}
                    className="border-b border-border last:border-0"
                  >
                    <td className="px-md py-sm font-mono text-small text-foreground">
                      {k.name || <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-md py-sm font-mono text-micro text-foreground">
                      {k.prefix}…
                    </td>
                    <td className="px-md py-sm font-mono text-micro tabular-nums text-muted-foreground">
                      {new Date(k.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-md py-sm font-mono text-micro tabular-nums text-muted-foreground">
                      {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-md py-sm">
                      {k.revoked_at ? (
                        <span className="font-mono text-micro uppercase tracking-wider text-muted-foreground line-through">Revoked</span>
                      ) : (
                        <span className="font-mono text-micro uppercase tracking-wider text-foreground">Active</span>
                      )}
                    </td>
                    <td className="px-md py-sm text-right">
                      {!k.revoked_at && (
                        <button
                          onClick={() => setConfirmRevoke(k.id)}
                          className="font-mono text-micro uppercase tracking-wider text-muted-foreground transition-colors hover:text-[#ea580c]"
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
        <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          Install
        </div>
        <h2 className="mb-lg font-mono text-xl font-bold uppercase text-foreground">
          Quick start
        </h2>
        <div className="space-y-md">
          <CodeBlock label="pip install" code={pipSnippet} />
          <CodeBlock label=".env" code={envSnippet} />
          <CodeBlock label="GitHub Action (steps:)" code={ghYaml} />
        </div>
      </section>

      {/* Usage */}
      <UsagePanel />

      {/* Audit log */}
      <AuditPanel projectId={projectId} />
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
      await loadStatus();
      // Clear the sensitive bot token from the form and collapse the
      // disclosure back down — the status card above now shows "Connected",
      // so there's no reason to keep the form (or the token) on screen.
      setChannelId("");
      setBotToken("");
      setManualSuccess(true);
      setAdvancedOpen(false);
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
        <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          Notifications
        </div>
        <h2 className="font-mono text-xl font-bold uppercase text-foreground">Slack alerts</h2>
        <p className="mt-sm font-mono text-small text-muted-foreground">
          AgentDiff posts a verdict card to your Slack channel whenever a CI run
          completes or a live drift anomaly is detected.
        </p>
      </div>

      {/* Banners from OAuth redirect */}
      {oauthBanner === "connected" && (
        <div className="border-2 border-foreground bg-background px-md py-sm font-mono text-small text-foreground">
          Slack connected successfully.
        </div>
      )}
      {oauthBanner === "error" && (
        <div className="border-2 border-[#ea580c] bg-background px-md py-sm font-mono text-small text-[#ea580c]">
          Slack connection failed. Please try again.
        </div>
      )}

      {/* Status card */}
      <div className="border-2 border-foreground bg-background p-lg">
        {statusLoading ? (
          <div className="h-10 animate-pulse border-2 border-foreground bg-muted" />
        ) : status?.connected ? (
          <div className="flex items-center justify-between gap-md">
            <div>
              <div className="mb-2xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
                Connected
              </div>
              <div className="flex items-center gap-sm">
                <span className="font-mono text-small text-foreground">
                  {status.channel_id ?? "—"}
                </span>
                <span
                  className={cn(
                    "inline-flex items-center border-2 px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest",
                    status.via === "oauth"
                      ? "border-foreground text-foreground"
                      : "border-border text-muted-foreground",
                  )}
                >
                  {status.via ?? "—"}
                </span>
              </div>
            </div>
            {!confirmDisconnect ? (
              <button
                onClick={() => setConfirmDisconnect(true)}
                className="border-2 border-foreground px-md py-sm font-mono text-small font-medium uppercase tracking-wider text-muted-foreground transition-colors hover:border-[#ea580c] hover:text-[#ea580c]"
              >
                Disconnect
              </button>
            ) : (
              <div className="flex items-center gap-sm">
                <span className="font-mono text-small text-muted-foreground">Confirm?</span>
                <button
                  onClick={() => setConfirmDisconnect(false)}
                  className="border-2 border-foreground px-sm py-2xs font-mono text-small text-foreground"
                >
                  Cancel
                </button>
                <button
                  onClick={() => void handleDisconnect()}
                  disabled={disconnecting}
                  className="bg-[#ea580c] px-sm py-2xs font-mono text-small font-medium uppercase tracking-wider text-background disabled:opacity-40"
                >
                  {disconnecting ? "Removing…" : "Remove"}
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-md">
            <p className="font-mono text-small text-muted-foreground">
              Click <strong>Add to Slack</strong> to connect your workspace. You'll pick a
              channel in Slack's native consent screen — no manual token setup required.
            </p>
            {installError && (
              <div className="border-2 border-[#ea580c] bg-background px-md py-sm font-mono text-small text-[#ea580c]">
                {installError}
              </div>
            )}
            <button
              onClick={() => void handleAddToSlack()}
              disabled={installing}
              className="bg-foreground px-lg py-sm font-mono text-small font-medium uppercase tracking-wider text-background transition-opacity disabled:opacity-40"
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
          aria-expanded={advancedOpen}
          className="flex items-center gap-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground transition-colors hover:text-foreground"
        >
          <span aria-hidden="true">{advancedOpen ? "▾" : "▸"}</span>
          Advanced: manual setup
        </button>

        {/* Success/error banners persist even after the form collapses on
            success, so the confirmation isn't lost the moment it appears. */}
        {manualSuccess && !advancedOpen && (
          <div className="mt-md border-2 border-foreground bg-background px-md py-sm font-mono text-small text-foreground">
            Slack configuration saved.
          </div>
        )}

        {advancedOpen && (
          <div className="mt-md space-y-md">
            <div className="border-2 border-foreground bg-background p-lg font-mono text-small text-muted-foreground">
              <p className="mb-sm font-medium text-foreground">How to create the Slack app:</p>
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
              <div className="border-2 border-foreground bg-background px-md py-sm font-mono text-small text-foreground">
                Slack configuration saved.
              </div>
            )}

            {manualError && (
              <div className="border-2 border-[#ea580c] bg-background px-md py-sm font-mono text-small text-[#ea580c]">
                {manualError}
              </div>
            )}

            <form onSubmit={(e) => void handleManualSubmit(e)} className="space-y-md">
              <div>
                <label className="mb-xs block font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
                  Channel ID
                </label>
                <input
                  value={channelId}
                  onChange={(e) => setChannelId(e.target.value)}
                  placeholder="C0123ABC456"
                  className="w-full border-2 border-foreground bg-background px-md py-sm font-mono text-small text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-foreground"
                />
              </div>
              <div>
                <label className="mb-xs block font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
                  Bot token
                </label>
                <input
                  type="password"
                  value={botToken}
                  onChange={(e) => setBotToken(e.target.value)}
                  placeholder="xoxb-…"
                  className="w-full border-2 border-foreground bg-background px-md py-sm font-mono text-small text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-foreground"
                />
              </div>
              <button
                type="submit"
                disabled={saving || !channelId.trim() || !botToken.trim()}
                className="bg-foreground px-lg py-sm font-mono text-small font-medium uppercase tracking-wider text-background transition-opacity disabled:opacity-40"
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

// ── Project header (rename inline + delete with typed confirmation) ───────────

function ProjectHeader({
  projectId,
  name,
  onRenamed,
}: {
  projectId: string;
  name: string | null;
  onRenamed: (name: string) => void;
}) {
  const { getToken } = useAuth();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name ?? "");
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [deleting, setDeleting] = useState(false);

  const displayName = name ?? "Project";

  // Escape closes the delete-project confirmation modal.
  useEffect(() => {
    if (!confirmDelete) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setConfirmDelete(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [confirmDelete]);

  async function save() {
    // Synchronous re-entrancy guard: a single "Save" click fires the input's
    // onBlur and the form's onSubmit before a `saving` state update flushes, so
    // a ref (not state) is what reliably collapses them into one PATCH.
    if (savingRef.current) return;
    const next = draft.trim();
    if (!next || next === name) {
      setEditing(false);
      return;
    }
    savingRef.current = true;
    setSaving(true);
    try {
      const updated = await renameProject(projectId, next, getToken);
      onRenamed(updated.name);
      setEditing(false);
      toast("Project renamed");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed to rename project", "error");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  async function doDelete() {
    setDeleting(true);
    try {
      await deleteProject(projectId, getToken);
      toast("Project deleted");
      navigate("/projects");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed to delete project", "error");
      setDeleting(false);
    }
  }

  return (
    <div className="mb-2xl flex items-start justify-between gap-md">
      {editing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
          className="flex items-center gap-sm"
        >
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => void save()}
            className="border-2 border-foreground bg-background px-md py-sm font-mono text-2xl font-bold uppercase text-foreground focus:outline-none focus:ring-1 focus:ring-foreground"
          />
          <button
            type="submit"
            disabled={saving}
            className="bg-foreground px-md py-sm font-mono text-small font-medium uppercase tracking-wider text-background disabled:opacity-40"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </form>
      ) : (
        <div className="group flex items-center gap-sm">
          <h1 className="font-mono text-2xl font-bold uppercase tracking-tight text-foreground">{displayName}</h1>
          <button
            onClick={() => {
              setDraft(name ?? "");
              setEditing(true);
            }}
            className="font-mono text-micro uppercase tracking-wider text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100"
          >
            Rename
          </button>
        </div>
      )}

      <button
        onClick={() => {
          setConfirmText("");
          setConfirmDelete(true);
        }}
        className="mt-xs border-2 border-foreground px-md py-sm font-mono text-small font-medium uppercase tracking-wider text-muted-foreground transition-colors hover:border-[#ea580c] hover:text-[#ea580c]"
      >
        Delete project
      </button>

      {/* Typed-confirmation delete modal */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 backdrop-blur-sm">
          <div className="mx-4 w-full max-w-md border-2 border-foreground bg-background p-xl">
            <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-[#ea580c]">
              Danger
            </div>
            <h2 className="mb-sm font-mono text-xl font-bold uppercase text-foreground">Delete project?</h2>
            <p className="mb-lg font-mono text-small text-muted-foreground">
              This permanently deletes <strong className="text-foreground">{displayName}</strong>{" "}
              and every run, key, and setting it holds. This cannot be undone. Type the project
              name to confirm.
            </p>
            <input
              autoFocus
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={displayName}
              className="mb-lg w-full border-2 border-foreground bg-background px-md py-sm font-mono text-small text-foreground placeholder:text-muted-foreground focus:border-[#ea580c] focus:outline-none"
            />
            <div className="flex gap-md">
              <button
                onClick={() => setConfirmDelete(false)}
                className="flex-1 border-2 border-foreground px-md py-sm font-mono text-small font-medium uppercase tracking-wider text-foreground transition-colors hover:bg-foreground hover:text-background"
              >
                Cancel
              </button>
              <button
                onClick={() => void doDelete()}
                disabled={deleting || confirmText.trim() !== displayName}
                className="flex-1 bg-[#ea580c] px-md py-sm font-mono text-small font-medium uppercase tracking-wider text-background disabled:opacity-40"
              >
                {deleting ? "Deleting…" : "Delete forever"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── ProjectPage ───────────────────────────────────────────────────────────────

export function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = id ?? "";
  const { getToken } = useAuth();
  const [tab, setTab] = useState("runs");
  const [projectName, setProjectName] = useState<string | null>(null);
  // Tri-state so the tab UI doesn't flash before the existence probe resolves.
  const [probe, setProbe] = useState<"pending" | "found" | "notfound">("pending");

  // Validate the project exists and belongs to this org, and grab its name.
  // On 404/403, show the not-found card instead of tabs.
  useEffect(() => {
    if (!projectId) { setProbe("notfound"); return; }
    setProbe("pending");
    // Resolve the project (name + existence) from the org's project list. No
    // GET /v1/projects/:id endpoint exists, so we match by id in the listing.
    fetchProjects(getToken)
      .then((page) => {
        const found = page.items.find((p) => p.id === projectId);
        if (found) {
          setProjectName(found.name);
          setProbe("found");
        } else {
          setProbe("notfound");
        }
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && (e.status === 404 || e.status === 403)) {
          setProbe("notfound");
        } else {
          // Transient/network error — don't hard-fail into not-found; let the
          // tab contents surface their own error state.
          setProbe("found");
        }
      });
  }, [projectId, getToken]);

  if (probe === "pending") {
    return (
      <div className="mx-auto w-full max-w-[1240px] px-xl py-2xl">
        <div className="mb-xl flex items-center gap-xs font-mono text-micro uppercase tracking-wider text-muted-foreground">
          <Link to="/projects" className="transition-colors hover:text-foreground">Projects</Link>
          <span>/</span>
          <span className="text-foreground">{projectId.slice(0, 8)}…</span>
        </div>
        <div className="h-40 animate-pulse border-2 border-foreground bg-muted" />
      </div>
    );
  }

  if (probe === "notfound") {
    return (
      <div className="mx-auto w-full max-w-[1240px] px-xl py-2xl">
        <div className="mb-xl flex items-center gap-xs font-mono text-micro uppercase tracking-wider text-muted-foreground">
          <Link to="/projects" className="transition-colors hover:text-foreground">Projects</Link>
          <span>/</span>
          <span className="text-foreground">{projectId.slice(0, 8)}…</span>
        </div>
        <div className="border-2 border-foreground bg-background p-2xl text-center">
          <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
            Project not found
          </div>
          <h2 className="mb-sm font-mono text-xl font-bold uppercase text-foreground">
            This project doesn&apos;t exist
          </h2>
          <p className="mb-lg max-w-md mx-auto font-mono text-small text-muted-foreground">
            Project <code className="font-mono text-foreground">{projectId.slice(0, 8)}…</code>{" "}
            was not found in your organisation, or it was deleted.
          </p>
          <Link
            to="/projects"
            className="inline-block bg-foreground px-lg py-sm font-mono text-small font-medium uppercase tracking-wider text-background transition-opacity hover:opacity-80"
          >
            Back to Projects
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[1240px] px-xl py-2xl">
      {/* Breadcrumb */}
      <div className="mb-xl flex items-center gap-xs font-mono text-micro uppercase tracking-wider text-muted-foreground">
        <Link to="/projects" className="transition-colors hover:text-foreground">
          Projects
        </Link>
        <span>/</span>
        <span className="text-foreground">{projectName ?? `${projectId.slice(0, 8)}…`}</span>
      </div>

      <ProjectHeader
        projectId={projectId}
        name={projectName}
        onRenamed={(n) => setProjectName(n)}
      />

      <Tabs.Root value={tab} onValueChange={setTab}>
        <Tabs.List className="mb-xl flex w-fit border-2 border-foreground">
          {(["runs", "setup", "slack"] as const).map((t, i) => (
            <Tabs.Trigger
              key={t}
              value={t}
              className={cn(
                "px-md py-sm font-mono text-micro uppercase tracking-widest transition-colors",
                i > 0 && "border-l-2 border-foreground",
                tab === t
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground",
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

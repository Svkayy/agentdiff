import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import { fetchRun, fetchRunPayload, ApiError, type RunDetail } from "@/lib/api";
import { toReportData } from "@/lib/payloadAdapter";
import { cn } from "@/lib/utils";
import type { ReportData } from "@/types";
import { verdictLabel } from "./ProjectPage";
import { Overview } from "@/sections/Overview";
import { BehavioralDeltas } from "@/sections/BehavioralDeltas";
import { Attribution } from "@/sections/Attribution";
import { Timeline } from "@/sections/Timeline";
import { RunSummary } from "@/sections/RunSummary";

// ── Verdict / kind badges ─────────────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: string | null }) {
  const styles: Record<string, string> = {
    pass: "bg-verdict-pass/10 text-verdict-pass border border-verdict-pass/30",
    warn: "bg-verdict-warn/10 text-verdict-warn border border-verdict-warn/30",
    fail: "bg-ember/10 text-ember border border-ember/30",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm px-sm py-2xs font-mono text-micro font-bold uppercase tracking-widest",
        verdict ? styles[verdict] ?? "border border-hairline text-neutral-faint" : "text-neutral-faint",
      )}
      title={verdict ?? undefined}
    >
      {verdictLabel(verdict)}
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

// ── Not-found card ────────────────────────────────────────────────────────────

function NotFoundCard({ runId }: { runId: string }) {
  return (
    <div className="rounded-md border border-hairline bg-white p-2xl text-center">
      <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
        Run not found
      </div>
      <h2 className="mb-sm font-display text-h2 font-bold text-ink-dark">
        This run isn&apos;t in your project
      </h2>
      <p className="mb-lg max-w-md mx-auto text-small text-neutral-muted">
        Run <code className="font-mono text-ink-dark">{runId.slice(0, 8)}…</code>{" "}
        doesn&apos;t belong to your current project, or it was deleted. Check that you&apos;re
        logged into the correct organisation.
      </p>
      <Link
        to="/"
        className="rounded-sm bg-ink-dark px-lg py-sm text-small font-medium text-white transition-opacity hover:opacity-80"
      >
        Back to Projects
      </Link>
    </div>
  );
}

// ── Export / share ────────────────────────────────────────────────────────────

function DownloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3v12m0 0-4-4m4 4 4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function LinkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M9 17H7A5 5 0 0 1 7 7h2m6 0h2a5 5 0 0 1 0 10h-2M8 12h8"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ExportBar({ runId, payload }: { runId: string; payload: ReportData | null }) {
  const [copied, setCopied] = useState(false);

  const downloadJson = useCallback(() => {
    if (!payload) return;
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `agentdiff-run-${runId.slice(0, 8)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, [payload, runId]);

  const copyLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore clipboard errors — non-critical affordance
    }
  }, []);

  return (
    <div className="flex items-center gap-xs">
      <button
        type="button"
        onClick={downloadJson}
        disabled={!payload}
        aria-label="Download run payload as JSON"
        title="Download run payload as JSON"
        className="flex items-center gap-xs rounded-sm border border-hairline bg-white px-sm py-2xs font-mono text-micro text-neutral-muted transition-colors hover:border-ink-dark hover:text-ink-dark disabled:cursor-not-allowed disabled:opacity-40"
      >
        <DownloadIcon />
        <span>Download JSON</span>
      </button>
      <button
        type="button"
        onClick={() => void copyLink()}
        aria-label="Copy link to this run"
        title="Copy link to this run"
        className="flex items-center gap-xs rounded-sm border border-hairline bg-white px-sm py-2xs font-mono text-micro text-neutral-muted transition-colors hover:border-ink-dark hover:text-ink-dark"
      >
        <LinkIcon />
        <span>{copied ? "Copied!" : "Copy link"}</span>
      </button>
    </div>
  );
}

// ── Rigor banners: low-power warnings + eval-incomplete skipped checks ───────

function RigorBanners({ data }: { data: ReportData }) {
  const skippedCount = data.outputEvals.reduce((n, e) => n + e.skipped_checks.length, 0);
  if (data.warnings.length === 0 && skippedCount === 0) return null;

  return (
    <div className="mb-xl space-y-sm">
      {data.warnings.length > 0 && (
        <div className="rounded-md border border-verdict-warn/30 bg-verdict-warn/5 px-lg py-md">
          <div className="mb-xs font-mono text-micro font-bold uppercase tracking-widest text-verdict-warn">
            Low statistical power
          </div>
          <ul className="list-inside list-disc space-y-2xs text-small text-ink-dark">
            {data.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      {skippedCount > 0 && (
        <div className="rounded-md border border-verdict-warn/30 bg-verdict-warn/5 px-lg py-md">
          <div className="mb-xs font-mono text-micro font-bold uppercase tracking-widest text-verdict-warn">
            Evaluation incomplete
          </div>
          <ul className="list-inside list-disc space-y-2xs text-small text-ink-dark">
            {data.outputEvals.flatMap((e) =>
              e.skipped_checks.map((s, i) => (
                <li key={`${e.test_case_id}-${s.check}-${i}`}>
                  <code className="font-mono text-micro">{e.test_case_id}</code>: {s.check} skipped
                  — {s.reason}
                </li>
              )),
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Tab bar ───────────────────────────────────────────────────────────────────

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "deltas", label: "Behavioral Deltas" },
  { id: "attribution", label: "Attribution" },
  { id: "timeline", label: "Timeline" },
  { id: "summary", label: "Summary" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function TabBar({ active, onChange }: { active: TabId; onChange: (id: TabId) => void }) {
  return (
    <div role="tablist" aria-label="Run report sections" className="flex flex-wrap gap-xs border-b border-hairline">
      {TABS.map((tab) => {
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls={`panel-${tab.id}`}
            id={`tab-${tab.id}`}
            onClick={() => onChange(tab.id)}
            className={cn(
              "rounded-t-sm px-md py-sm font-mono text-small transition-colors duration-[80ms] -mb-px",
              isActive
                ? "border-b-2 border-ink-dark text-ink-dark"
                : "text-neutral-faint hover:text-ink-dark",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

function ReportPanel({ data }: { data: ReportData }) {
  const [active, setActive] = useState<TabId>("overview");

  return (
    <div>
      <TabBar active={active} onChange={setActive} />
      <RigorBanners data={data} />
      <div
        role="tabpanel"
        id={`panel-${active}`}
        aria-labelledby={`tab-${active}`}
        className="rounded-lg border border-node-border p-xl"
        style={{ background: "#0E1116" }}
      >
        {active === "overview" && <Overview data={data} />}
        {active === "deltas" && <BehavioralDeltas data={data} />}
        {active === "attribution" && <Attribution data={data} />}
        {active === "timeline" && <Timeline data={data} />}
        {active === "summary" && <RunSummary data={data} />}
      </div>
    </div>
  );
}

// ── Payload loading states ───────────────────────────────────────────────────

const POLL_MS = 5000;

function usePayload(runId: string, status: string | null, getToken: () => Promise<string | null>) {
  const [payload, setPayload] = useState<ReportData | null>(null);
  const [payloadPending, setPayloadPending] = useState(false);
  const [payloadError, setPayloadError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;

    const clearTimer = () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    const load = () => {
      fetchRunPayload(runId, getToken)
        .then((raw) => {
          if (cancelled) return;
          setPayload(toReportData(raw));
          setPayloadPending(false);
          setPayloadError(null);
        })
        .catch((e: unknown) => {
          if (cancelled) return;
          const notReady = e instanceof ApiError && e.status === 404;
          if (notReady && (status === "pending" || status === "processing")) {
            setPayloadPending(true);
            setPayloadError(null);
            timerRef.current = setTimeout(load, POLL_MS);
            return;
          }
          if (notReady) {
            setPayloadPending(true);
            setPayloadError(null);
            return;
          }
          setPayloadPending(false);
          setPayloadError(e instanceof Error ? e.message : "Failed to load run report");
        });
    };

    load();
    return () => {
      cancelled = true;
      clearTimer();
    };
  }, [runId, status, getToken]);

  return { payload, payloadPending, payloadError };
}

// ── RunDetailPage ─────────────────────────────────────────────────────────────

export function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const runId = id ?? "";
  const { getToken } = useAuth();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setNotFound(false);
    fetchRun(runId, getToken)
      .then((data) => {
        setRun(data);
        setError(null);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && (e.status === 404 || e.status === 403)) {
          setNotFound(true);
        } else {
          setError(e instanceof Error ? e.message : "Failed to load run");
        }
      })
      .finally(() => setLoading(false));
  }, [runId, getToken]);

  const { payload, payloadPending, payloadError } = usePayload(runId, run?.status ?? null, getToken);

  return (
    <div className="mx-auto w-full max-w-[1240px] px-xl py-2xl">
      {/* Breadcrumb */}
      <div className="mb-xl flex items-center gap-xs font-mono text-micro text-neutral-faint">
        <Link to="/" className="transition-colors hover:text-ink-dark">
          Projects
        </Link>
        <span>/</span>
        {run && (
          <>
            <span className="text-ink-dark">Run</span>
            <span>/</span>
          </>
        )}
        <span className="text-ink-dark">{runId.slice(0, 8)}…</span>
      </div>

      {loading && (
        <div className="space-y-md">
          <div className="h-10 w-64 animate-pulse rounded-sm border border-hairline bg-hairline" />
          <div className="h-64 animate-pulse rounded-md border border-hairline bg-hairline" />
        </div>
      )}

      {/* Graceful not-found: 404/403 → clear card with back-link, never blank */}
      {!loading && notFound && <NotFoundCard runId={runId} />}

      {!loading && error && (
        <div className="rounded-sm border border-ember/30 bg-ember/5 px-md py-sm text-small text-ember">
          {error}
        </div>
      )}

      {run && (
        <>
          {/* Header */}
          <div className="mb-2xl flex flex-wrap items-start justify-between gap-md">
            <div>
              <div className="mb-sm flex flex-wrap items-center gap-sm">
                <VerdictBadge verdict={run.verdict} />
                <KindBadge kind={run.kind} />
                <span className="font-mono text-micro text-neutral-faint">
                  {new Date(run.created_at).toLocaleString()}
                </span>
              </div>
              <h1 className="font-display text-h1 font-bold text-ink-dark">Run detail</h1>
              <div className="mt-xs font-mono text-micro text-neutral-faint">
                <span className="text-ink-dark">{run.baseline_ref}</span>
                <span className="mx-xs">→</span>
                <span className="text-ink-dark">{run.candidate_ref}</span>
                <span className="mx-sm text-neutral-faint">·</span>
                <span>
                  n={run.baseline_samples} vs {run.candidate_samples} samples
                </span>
              </div>
            </div>
            <ExportBar runId={runId} payload={payload} />
          </div>

          {/* Failed run banner — show engine error prominently before the report */}
          {run.status === "failed" && run.error && (
            <div className="mb-2xl rounded-md border border-ember/30 bg-ember/5 p-lg">
              <div className="mb-xs font-mono text-micro font-bold uppercase tracking-widest text-ember">
                Run failed
              </div>
              <pre className="whitespace-pre-wrap font-mono text-micro text-ember">
                {run.error}
              </pre>
            </div>
          )}

          {/* Five-view report, once the payload is ready */}
          {run.status !== "failed" && (
            <>
              {payloadPending && (
                <div className="rounded-md border border-hairline bg-white p-2xl text-center">
                  <div className="mb-xs font-mono text-micro uppercase tracking-widest text-neutral-faint">
                    Processing
                  </div>
                  <h2 className="mb-sm font-display text-h2 font-bold text-ink-dark">
                    Report isn&apos;t ready yet
                  </h2>
                  <p className="text-small text-neutral-muted">
                    This run is still being processed — checking again every 5 seconds.
                  </p>
                </div>
              )}

              {!payloadPending && payloadError && (
                <div className="rounded-sm border border-ember/30 bg-ember/5 px-md py-sm text-small text-ember">
                  {payloadError}
                </div>
              )}

              {!payloadPending && !payloadError && payload && <ReportPanel data={payload} />}
            </>
          )}

          {/* Engine error on non-failed runs (e.g. partial error) */}
          {run.status !== "failed" && run.error && (
            <div className="mt-2xl rounded-sm border border-ember/30 bg-ember/5 px-md py-sm">
              <div className="mb-xs font-mono text-micro uppercase tracking-widest text-ember">
                Run error
              </div>
              <pre className="whitespace-pre-wrap font-mono text-micro text-ember">
                {run.error}
              </pre>
            </div>
          )}
        </>
      )}
    </div>
  );
}

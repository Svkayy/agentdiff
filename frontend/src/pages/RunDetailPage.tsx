import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import { fetchRun, fetchRunPayload, ApiError, type RunDetail } from "@/lib/api";
import { toReportData } from "@/lib/payloadAdapter";
import { cn } from "@/lib/utils";
import { RunReportPanel } from "@/components/RunReportPanel";
import type { ReportData } from "@/types";
import { verdictLabel } from "./ProjectPage";

// ── Verdict / kind badges ─────────────────────────────────────────────────────

// Verdict mapping (DESIGN.md, locked): pass = neutral/foreground chip;
// warn = orange OUTLINE; fail = solid #ea580c.
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

// ── Not-found card ────────────────────────────────────────────────────────────

function NotFoundCard({ runId }: { runId: string }) {
  return (
    <div className="border-2 border-foreground bg-background p-2xl text-center">
      <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
        Run not found
      </div>
      <h2 className="mb-sm font-mono text-xl font-bold uppercase text-foreground">
        This run isn&apos;t in your project
      </h2>
      <p className="mb-lg max-w-md mx-auto font-mono text-small text-muted-foreground">
        Run <code className="font-mono text-foreground">{runId.slice(0, 8)}…</code>{" "}
        doesn&apos;t belong to your current project, or it was deleted. Check that you&apos;re
        logged into the correct organisation.
      </p>
      <Link
        to="/projects"
        className="inline-block bg-foreground px-lg py-sm font-mono text-small font-medium uppercase tracking-wider text-background transition-opacity hover:opacity-80"
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

function ExportBar({ runId, payload }: { runId: string; payload: unknown }) {
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
        className="flex items-center gap-xs border-2 border-foreground bg-background px-sm py-2xs font-mono text-micro uppercase tracking-wider text-foreground transition-colors hover:bg-foreground hover:text-background disabled:cursor-not-allowed disabled:opacity-40"
      >
        <DownloadIcon />
        <span>Download JSON</span>
      </button>
      <button
        type="button"
        onClick={() => void copyLink()}
        aria-label="Copy link to this run"
        title="Copy link to this run"
        className="flex items-center gap-xs border-2 border-foreground bg-background px-sm py-2xs font-mono text-micro uppercase tracking-wider text-foreground transition-colors hover:bg-foreground hover:text-background"
      >
        <LinkIcon />
        <span>{copied ? "Copied!" : "Copy link"}</span>
      </button>
    </div>
  );
}

// ── Payload loading states ───────────────────────────────────────────────────

const POLL_MS = 5000;

/** Bound on in-progress polling so a stuck "processing" run doesn't poll forever. */
const MAX_POLL_ATTEMPTS = 200; // ~16.6 minutes at 5s intervals

export function usePayload(
  runId: string,
  status: string | null,
  getToken: () => Promise<string | null>,
  retryKey = 0,
) {
  const [payload, setPayload] = useState<ReportData | null>(null);
  const [rawPayload, setRawPayload] = useState<unknown>(null);
  const [payloadPending, setPayloadPending] = useState(false);
  const [payloadError, setPayloadError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    let attempts = 0;

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
          setRawPayload(raw);
          setPayload(toReportData(raw));
          setPayloadPending(false);
          setPayloadError(null);
        })
        .catch((e: unknown) => {
          if (cancelled) return;
          const notReady = e instanceof ApiError && e.status === 404;
          const inProgress = status === "pending" || status === "processing";

          if (notReady && inProgress) {
            attempts += 1;
            if (attempts >= MAX_POLL_ATTEMPTS) {
              // Give up after a bounded number of retries rather than polling forever.
              setPayloadPending(false);
              setPayloadError("Report data is unavailable for this run.");
              return;
            }
            setPayloadPending(true);
            setPayloadError(null);
            timerRef.current = setTimeout(load, POLL_MS);
            return;
          }

          if (notReady) {
            // Run is in a terminal state (completed/failed/unknown) but the payload
            // still 404s — this is a real error, not "not ready yet". No further
            // polling: nothing will make a terminal run's missing payload appear.
            setPayloadPending(false);
            setPayloadError("Report data is unavailable for this run.");
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
  }, [runId, status, getToken, retryKey]);

  return { payload, rawPayload, payloadPending, payloadError };
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

  const [payloadRetryKey, setPayloadRetryKey] = useState(0);
  const { payload, rawPayload, payloadPending, payloadError } = usePayload(
    runId,
    run?.status ?? null,
    getToken,
    payloadRetryKey,
  );

  return (
    <div className="mx-auto w-full max-w-[1240px] px-xl py-2xl">
      {/* Breadcrumb */}
      <div className="mb-xl flex items-center gap-xs font-mono text-micro uppercase tracking-wider text-muted-foreground">
        <Link to="/projects" className="transition-colors hover:text-foreground">
          Projects
        </Link>
        <span>/</span>
        {run && (
          <>
            <span className="text-foreground">Run</span>
            <span>/</span>
          </>
        )}
        <span className="text-foreground">{runId.slice(0, 8)}…</span>
      </div>

      {loading && (
        <div className="space-y-md">
          <div className="h-10 w-64 animate-pulse border-2 border-foreground bg-muted" />
          <div className="h-64 animate-pulse border-2 border-foreground bg-muted" />
        </div>
      )}

      {/* Graceful not-found: 404/403 → clear card with back-link, never blank */}
      {!loading && notFound && <NotFoundCard runId={runId} />}

      {!loading && error && (
        <div className="border-2 border-[#ea580c] bg-background px-md py-sm font-mono text-small text-[#ea580c]">
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
                <span className="font-mono text-micro tabular-nums text-muted-foreground">
                  {new Date(run.created_at).toLocaleString()}
                </span>
              </div>
              <h1 className="font-mono text-2xl font-bold uppercase tracking-tight text-foreground">Run detail</h1>
              <div className="mt-xs font-mono text-micro text-muted-foreground">
                <span className="text-foreground">{run.baseline_ref}</span>
                <span className="mx-xs">→</span>
                <span className="text-foreground">{run.candidate_ref}</span>
                <span className="mx-sm text-muted-foreground">·</span>
                <span className="tabular-nums">
                  n={run.baseline_samples} vs {run.candidate_samples} samples
                </span>
              </div>
            </div>
            <ExportBar runId={runId} payload={rawPayload} />
          </div>

          {/* Failed run banner — show engine error prominently before the report */}
          {run.status === "failed" && run.error && (
            <div className="mb-2xl border-2 border-[#ea580c] bg-background p-lg">
              <div className="mb-xs font-mono text-xs font-bold uppercase tracking-[0.2em] text-[#ea580c]">
                Run failed
              </div>
              <pre className="whitespace-pre-wrap font-mono text-micro text-[#ea580c]">
                {run.error}
              </pre>
            </div>
          )}

          {/* Five-view report, once the payload is ready */}
          {run.status !== "failed" && (
            <>
              {payloadPending && (
                <div className="border-2 border-foreground bg-background p-2xl text-center">
                  <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
                    Processing
                  </div>
                  <h2 className="mb-sm font-mono text-xl font-bold uppercase text-foreground">
                    Report isn&apos;t ready yet
                  </h2>
                  <p className="font-mono text-small text-muted-foreground">
                    This run is still being processed — checking again every 5 seconds.
                  </p>
                </div>
              )}

              {!payloadPending && payloadError && (
                <div className="border-2 border-[#ea580c] bg-background p-2xl text-center">
                  <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-[#ea580c]">
                    Error
                  </div>
                  <h2 className="mb-sm font-mono text-xl font-bold uppercase text-foreground">
                    Report unavailable
                  </h2>
                  <p className="mb-lg font-mono text-small text-muted-foreground">{payloadError}</p>
                  <button
                    type="button"
                    onClick={() => setPayloadRetryKey((k) => k + 1)}
                    className="bg-foreground px-lg py-sm font-mono text-small font-medium uppercase tracking-wider text-background transition-opacity hover:opacity-80"
                  >
                    Retry
                  </button>
                </div>
              )}

              {!payloadPending && !payloadError && payload && <RunReportPanel data={payload} />}
            </>
          )}

          {/* Engine error on non-failed runs (e.g. partial error) */}
          {run.status !== "failed" && run.error && (
            <div className="mt-2xl border-2 border-[#ea580c] bg-background px-md py-sm">
              <div className="mb-xs font-mono text-xs uppercase tracking-[0.2em] text-[#ea580c]">
                Run error
              </div>
              <pre className="whitespace-pre-wrap font-mono text-micro text-[#ea580c]">
                {run.error}
              </pre>
            </div>
          )}
        </>
      )}
    </div>
  );
}

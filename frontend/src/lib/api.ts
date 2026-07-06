import type {
  AgentGraph,
  Attribution,
  Comparison,
  StatisticalEvidence,
} from "@/types";
import { onUnauthorized } from "./auth";

const API_URL = import.meta.env.VITE_AGENTDIFF_API_URL ?? "http://localhost:8000";

export type GetToken = () => Promise<string | null>;

// ── Shared authenticated fetch ────────────────────────────────────────────────

/** Error thrown when the API returns a non-2xx status. Carries the HTTP status code. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Central error handler for API failures. On 401 it triggers `onUnauthorized`
 * (Clerk sign-out + redirect + toast) before re-throwing so callers still see
 * a rejected promise. Kept synchronous — it only fires a side effect.
 */
export function handleApiError(error: unknown): never {
  if (error instanceof ApiError && error.status === 401) {
    onUnauthorized();
  }
  throw error;
}

async function authed(
  path: string,
  getToken: GetToken,
  options?: RequestInit,
): Promise<unknown> {
  const token = await getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options?.headers ?? {}),
    },
  });
  if (!res.ok) handleApiError(new ApiError(res.status, `API ${res.status}`));
  // 204 No Content has no body.
  if (res.status === 204) return undefined;
  return res.json();
}

/** Envelope shape for paginated/searchable list endpoints (Task 11/12). */
export interface Page<T> {
  items: T[];
  total: number;
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Project {
  id: string;
  name: string;
}

export interface Run {
  id: string;
  status: string;
  verdict: string | null;
  baseline_ref: string;
  candidate_ref: string;
  kind: string;
  created_at: string;
}

export interface RunDetail extends Run {
  error: string | null;
  config: Record<string, unknown>;
  findings: Finding[];
  baseline_samples: number;
  candidate_samples: number;
  graph: AgentGraph | null;
  comparison: Comparison;
  attribution: Attribution | null;
  trajectories: {
    baseline: Record<string, unknown>[];
    candidate: Record<string, unknown>[];
  };
}

export interface Finding {
  test_case_id: string;
  title: string;
  verdict: string;
  metric: string;
  impact_summary: string;
  statistical_evidence: StatisticalEvidence | null;
  cause_path: string | null;
  cause_rule: string | null;
  cause_hunk: string | null;
  explanation: string | null;
  // Aggregation context: how many test cases are represented in this finding.
  test_cases_affected: number;
  test_cases_total: number;
}

export interface ProjectStats {
  total_runs: number;
  pass_rate_30: number | null;
  failing_streak: number;
  last_failure_at: string | null;
  drift_runs_7d: number;
  recent: Array<{
    id: string;
    verdict: string | null;
    kind: string;
    created_at: string;
  }>;
}

export interface ApiKey {
  id: string;
  name: string | null;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface MintedKey {
  id: string;
  key: string;
  prefix: string;
  name?: string | null;
}

export interface Usage {
  plan: string;
  period: string;
  runs_used: number;
  runs_limit: number | null; // null = unlimited
  trajectories_used: number;
  trajectories_limit: number | null; // null = unlimited
}

export interface AuditEntry {
  id: string;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  meta: Record<string, unknown> | null;
  created_at: string;
}

export interface Me {
  user: {
    id: string;
    email: string;
    clerk_user_id: string;
  };
  org: {
    id: string;
    name: string;
    clerk_org_id: string;
  };
}

// ── Read endpoints ────────────────────────────────────────────────────────────

export function fetchProjectStats(projectId: string, getToken: GetToken): Promise<ProjectStats> {
  return authed(`/v1/projects/${projectId}/stats`, getToken) as Promise<ProjectStats>;
}

export function fetchRuns(projectId: string, getToken: GetToken): Promise<Page<Run>> {
  return authed(`/v1/projects/${projectId}/runs`, getToken) as Promise<Page<Run>>;
}

/** Paginated + filterable runs list. Consumes the `{items,total}` envelope. */
export function fetchRunsPage(
  projectId: string,
  opts: { limit?: number; offset?: number; verdict?: string; q?: string },
  getToken: GetToken,
): Promise<Page<Run>> {
  const params = new URLSearchParams();
  if (opts.limit != null) params.set("limit", String(opts.limit));
  if (opts.offset != null) params.set("offset", String(opts.offset));
  if (opts.verdict) params.set("verdict", opts.verdict);
  if (opts.q) params.set("q", opts.q);
  const qs = params.toString();
  return authed(
    `/v1/projects/${projectId}/runs${qs ? `?${qs}` : ""}`,
    getToken,
  ) as Promise<Page<Run>>;
}

export function fetchRun(runId: string, getToken: GetToken): Promise<RunDetail> {
  return authed(`/v1/runs/${runId}`, getToken) as Promise<RunDetail>;
}

/**
 * The full report payload for a run (rendered by Task 14).
 * Returns the raw server JSON, unmapped — callers pass it through
 * `toReportData` (see payloadAdapter.ts) to get the typed `ReportData`
 * shape, or keep the raw value for e.g. JSON export.
 */
export function fetchRunPayload(runId: string, getToken: GetToken): Promise<unknown> {
  return authed(`/v1/runs/${runId}/payload`, getToken);
}

export function fetchProjects(getToken: GetToken, q?: string): Promise<Page<Project>> {
  const qs = q ? `?q=${encodeURIComponent(q)}` : "";
  return authed(`/v1/projects${qs}`, getToken) as Promise<Page<Project>>;
}

export function fetchUsage(getToken: GetToken): Promise<Usage> {
  return authed(`/v1/usage`, getToken) as Promise<Usage>;
}

export function fetchAudit(
  projectId: string,
  opts: { limit?: number; offset?: number },
  getToken: GetToken,
): Promise<Page<AuditEntry>> {
  const params = new URLSearchParams();
  if (opts.limit != null) params.set("limit", String(opts.limit));
  if (opts.offset != null) params.set("offset", String(opts.offset));
  const qs = params.toString();
  return authed(
    `/v1/projects/${projectId}/audit${qs ? `?${qs}` : ""}`,
    getToken,
  ) as Promise<Page<AuditEntry>>;
}

export function fetchMe(getToken: GetToken): Promise<Me> {
  return authed(`/v1/me`, getToken) as Promise<Me>;
}

export function listKeys(projectId: string, getToken: GetToken): Promise<ApiKey[]> {
  return authed(`/v1/projects/${projectId}/keys`, getToken) as Promise<ApiKey[]>;
}

// ── Write endpoints ───────────────────────────────────────────────────────────

export function createProject(name: string, getToken: GetToken): Promise<Project> {
  return authed(`/v1/projects`, getToken, {
    method: "POST",
    body: JSON.stringify({ name }),
  }) as Promise<Project>;
}

export function renameProject(
  projectId: string,
  name: string,
  getToken: GetToken,
): Promise<Project> {
  return authed(`/v1/projects/${projectId}`, getToken, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  }) as Promise<Project>;
}

export function deleteProject(projectId: string, getToken: GetToken): Promise<void> {
  return authed(`/v1/projects/${projectId}`, getToken, {
    method: "DELETE",
  }) as Promise<void>;
}

export function deleteRun(runId: string, getToken: GetToken): Promise<void> {
  return authed(`/v1/runs/${runId}`, getToken, {
    method: "DELETE",
  }) as Promise<void>;
}

export function mintKey(
  projectId: string,
  name: string | null,
  getToken: GetToken,
): Promise<MintedKey> {
  return authed(`/v1/projects/${projectId}/keys`, getToken, {
    method: "POST",
    body: JSON.stringify({ name }),
  }) as Promise<MintedKey>;
}

export function revokeKey(keyId: string, getToken: GetToken): Promise<void> {
  return authed(`/v1/keys/${keyId}`, getToken, {
    method: "DELETE",
  }) as Promise<void>;
}

export function putSlackConfig(
  projectId: string,
  channelId: string,
  botToken: string,
  getToken: GetToken,
): Promise<{ status: string }> {
  return authed(`/v1/projects/${projectId}/slack`, getToken, {
    method: "PUT",
    body: JSON.stringify({ channel_id: channelId, bot_token: botToken }),
  }) as Promise<{ status: string }>;
}

// ── Slack OAuth ───────────────────────────────────────────────────────────────

export interface SlackStatus {
  connected: boolean;
  channel_id: string | null;
  via: "oauth" | "manual" | null;
}

export interface SlackInstallUrl {
  url: string;
}

export function getSlackStatus(projectId: string, getToken: GetToken): Promise<SlackStatus> {
  return authed(`/v1/projects/${projectId}/slack`, getToken) as Promise<SlackStatus>;
}

export function getSlackInstallUrl(projectId: string, getToken: GetToken): Promise<SlackInstallUrl> {
  return authed(`/v1/slack/install?project_id=${projectId}`, getToken) as Promise<SlackInstallUrl>;
}

export function disconnectSlack(projectId: string, getToken: GetToken): Promise<void> {
  return authed(`/v1/projects/${projectId}/slack`, getToken, {
    method: "DELETE",
  }) as Promise<void>;
}

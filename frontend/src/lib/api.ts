const API_URL = import.meta.env.VITE_AGENTDIFF_API_URL ?? "http://localhost:8000";

export type GetToken = () => Promise<string | null>;

// ── Shared authenticated fetch ────────────────────────────────────────────────

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
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
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
}

export interface Finding {
  test_case_id: string;
  title: string;
  verdict: string;
  metric: string;
  impact_summary: string;
  cause_path: string | null;
  cause_rule: string | null;
}

export interface ApiKey {
  id: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface MintedKey {
  id: string;
  key: string;
  prefix: string;
}

export interface Me {
  id: string;
  email: string;
}

// ── Read endpoints ────────────────────────────────────────────────────────────

export function fetchRuns(projectId: string, getToken: GetToken): Promise<Run[]> {
  return authed(`/v1/projects/${projectId}/runs`, getToken) as Promise<Run[]>;
}

export function fetchRun(runId: string, getToken: GetToken): Promise<RunDetail> {
  return authed(`/v1/runs/${runId}`, getToken) as Promise<RunDetail>;
}

export function fetchProjects(getToken: GetToken): Promise<Project[]> {
  return authed(`/v1/projects`, getToken) as Promise<Project[]>;
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

export function mintKey(projectId: string, getToken: GetToken): Promise<MintedKey> {
  return authed(`/v1/projects/${projectId}/keys`, getToken, {
    method: "POST",
    body: JSON.stringify({}),
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

const API_URL = import.meta.env.VITE_AGENTDIFF_API_URL ?? "http://localhost:8000";

type GetToken = () => Promise<string | null>;

async function authed(path: string, getToken: GetToken) {
  const token = await getToken();
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export function fetchRuns(projectId: string, getToken: GetToken) {
  return authed(`/v1/projects/${projectId}/runs`, getToken);
}

export function fetchRun(runId: string, getToken: GetToken) {
  return authed(`/v1/runs/${runId}`, getToken);
}

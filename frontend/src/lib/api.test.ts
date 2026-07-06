import { describe, it, expect, vi, afterEach } from "vitest";
import {
  fetchRuns,
  fetchRunsPage,
  fetchRun,
  fetchRunPayload,
  fetchProjects,
  fetchUsage,
  fetchAudit,
  fetchMe,
  createProject,
  renameProject,
  deleteProject,
  deleteRun,
  mintKey,
  revokeKey,
  putSlackConfig,
  listKeys,
  getSlackStatus,
  getSlackInstallUrl,
  disconnectSlack,
  fetchProjectStats,
  ApiError,
} from "./api";
import * as auth from "./auth";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  auth.__resetUnauthorizedGuard();
});

// ── helpers ───────────────────────────────────────────────────────────────────

function stubFetch(body: unknown, ok = true, status = 200) {
  const calls: { url: string; opts: RequestInit }[] = [];
  vi.stubGlobal("fetch", async (url: string, opts: RequestInit) => {
    calls.push({ url, opts });
    return { ok, status, json: async () => body } as Response;
  });
  return calls;
}

function auth401() {
  const calls: { url: string; opts: RequestInit }[] = [];
  vi.stubGlobal("fetch", async (url: string, opts: RequestInit) => {
    calls.push({ url, opts });
    return { ok: false, status: 401, json: async () => ({}) } as Response;
  });
  return calls;
}

// ── existing tests (updated for {items,total} envelope) ────────────────────────

describe("fetchRuns", () => {
  it("returns the {items,total} envelope with the clerk bearer token", async () => {
    const calls = stubFetch({ items: [{ id: "r1" }], total: 1 });
    const runs = await fetchRuns("proj-1", async () => "jwt-abc");
    expect(runs).toEqual({ items: [{ id: "r1" }], total: 1 });
    expect(calls[0].url).toContain("/v1/projects/proj-1/runs");
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer jwt-abc",
    );
  });
});

describe("fetchRunsPage", () => {
  it("passes limit/offset/verdict/q as query params", async () => {
    const calls = stubFetch({ items: [], total: 0 });
    await fetchRunsPage(
      "proj-9",
      { limit: 20, offset: 40, verdict: "fail", q: "auth" },
      async () => "tok",
    );
    const url = calls[0].url;
    expect(url).toContain("/v1/projects/proj-9/runs?");
    expect(url).toContain("limit=20");
    expect(url).toContain("offset=40");
    expect(url).toContain("verdict=fail");
    expect(url).toContain("q=auth");
  });

  it("omits empty options from the query string", async () => {
    const calls = stubFetch({ items: [], total: 0 });
    await fetchRunsPage("proj-9", {}, async () => "tok");
    expect(calls[0].url).toContain("/v1/projects/proj-9/runs");
    expect(calls[0].url).not.toContain("?");
  });
});

describe("fetchRun", () => {
  it("fetches the correct run URL with bearer token", async () => {
    const stubbed = { id: "run-1", status: "done" };
    const calls = stubFetch(stubbed);
    const result = await fetchRun("run-1", async () => "jwt-xyz");
    expect(calls[0].url).toContain("/v1/runs/run-1");
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer jwt-xyz",
    );
    expect(result).toEqual(stubbed);
  });
});

describe("fetchRunPayload", () => {
  it("GET /v1/runs/:id/payload with bearer token", async () => {
    const calls = stubFetch({ meta: {}, graph: { nodes: [] } });
    await fetchRunPayload("run-7", async () => "tok-payload");
    expect(calls[0].url).toContain("/v1/runs/run-7/payload");
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer tok-payload",
    );
  });
});

describe("null-token guard", () => {
  it("rejects without calling fetch when token is null", async () => {
    const mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
    await expect(fetchRuns("p1", async () => null)).rejects.toThrow("Not authenticated");
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

// ── list endpoints ─────────────────────────────────────────────────────────────

describe("fetchProjects", () => {
  it("GET /v1/projects returns the {items,total} envelope", async () => {
    const calls = stubFetch({ items: [{ id: "p1", name: "my-proj" }], total: 1 });
    const projects = await fetchProjects(async () => "tok");
    expect(calls[0].url).toContain("/v1/projects");
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok");
    expect(projects).toEqual({ items: [{ id: "p1", name: "my-proj" }], total: 1 });
  });

  it("passes q as a query param when provided", async () => {
    const calls = stubFetch({ items: [], total: 0 });
    await fetchProjects(async () => "tok", "my search");
    expect(calls[0].url).toContain("q=my%20search");
  });
});

describe("fetchUsage", () => {
  it("GET /v1/usage returns plan + limits", async () => {
    const calls = stubFetch({
      plan: "pro",
      period: "2026-07",
      runs_used: 12,
      runs_limit: 100,
      trajectories_used: 340,
      trajectories_limit: null,
    });
    const usage = await fetchUsage(async () => "tok-usage");
    expect(calls[0].url).toContain("/v1/usage");
    expect(usage.plan).toBe("pro");
    expect(usage.runs_limit).toBe(100);
    expect(usage.trajectories_limit).toBeNull();
  });
});

describe("fetchAudit", () => {
  it("GET /v1/projects/:id/audit with limit/offset and envelope", async () => {
    const calls = stubFetch({
      items: [
        {
          id: "a1",
          actor: "user@x.com",
          action: "project.rename",
          target_type: "project",
          target_id: "p1",
          meta: { from: "old", to: "new" },
          created_at: "2026-07-01T00:00:00Z",
        },
      ],
      total: 1,
    });
    const result = await fetchAudit("proj-a", { limit: 25, offset: 0 }, async () => "tok-audit");
    expect(calls[0].url).toContain("/v1/projects/proj-a/audit?");
    expect(calls[0].url).toContain("limit=25");
    expect(calls[0].url).toContain("offset=0");
    expect(result.items[0].action).toBe("project.rename");
    expect(result.total).toBe(1);
  });
});

describe("fetchMe", () => {
  it("GET /v1/me with bearer token", async () => {
    const calls = stubFetch({
      user: { id: "u1", email: "x@x.com", clerk_user_id: "cu_1" },
      org: { id: "o1", name: "My Org", clerk_org_id: "co_1" },
    });
    const result = await fetchMe(async () => "tok2");
    expect(calls[0].url).toContain("/v1/me");
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok2");
    expect(result.user.id).toBe("u1");
    expect(result.user.email).toBe("x@x.com");
    expect(result.org.name).toBe("My Org");
  });
});

// ── project CRUD ────────────────────────────────────────────────────────────────

describe("createProject", () => {
  it("POST /v1/projects with name in body", async () => {
    const calls = stubFetch({ id: "p2", name: "new" });
    await createProject("new", async () => "tok3");
    expect(calls[0].url).toContain("/v1/projects");
    expect(calls[0].opts.method).toBe("POST");
    expect(calls[0].opts.body).toBe(JSON.stringify({ name: "new" }));
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok3");
  });
});

describe("renameProject", () => {
  it("PATCH /v1/projects/:id with name in body", async () => {
    const calls = stubFetch({ id: "p2", name: "renamed" });
    const result = await renameProject("p2", "renamed", async () => "tok-rn");
    expect(calls[0].url).toContain("/v1/projects/p2");
    expect(calls[0].opts.method).toBe("PATCH");
    expect(calls[0].opts.body).toBe(JSON.stringify({ name: "renamed" }));
    expect(result.name).toBe("renamed");
  });
});

describe("deleteProject", () => {
  it("DELETE /v1/projects/:id (204 no body)", async () => {
    const calls = stubFetch(undefined, true, 204);
    await deleteProject("p3", async () => "tok-dp");
    expect(calls[0].url).toContain("/v1/projects/p3");
    expect(calls[0].opts.method).toBe("DELETE");
  });
});

describe("deleteRun", () => {
  it("DELETE /v1/runs/:id (204 no body)", async () => {
    const calls = stubFetch(undefined, true, 204);
    await deleteRun("run-3", async () => "tok-dr");
    expect(calls[0].url).toContain("/v1/runs/run-3");
    expect(calls[0].opts.method).toBe("DELETE");
  });
});

describe("mintKey", () => {
  it("POST /v1/projects/:id/keys with name in body", async () => {
    const calls = stubFetch({ id: "k1", key: "adk_secret", prefix: "adk_", name: "ci" });
    const result = await mintKey("proj-5", "ci", async () => "tok4");
    expect(calls[0].url).toContain("/v1/projects/proj-5/keys");
    expect(calls[0].opts.method).toBe("POST");
    expect(calls[0].opts.body).toBe(JSON.stringify({ name: "ci" }));
    expect(result).toMatchObject({ prefix: "adk_", name: "ci" });
  });

  it("sends name: null when no name given", async () => {
    const calls = stubFetch({ id: "k2", key: "adk_x", prefix: "adk_" });
    await mintKey("proj-5", null, async () => "tok4");
    expect(calls[0].opts.body).toBe(JSON.stringify({ name: null }));
  });
});

describe("revokeKey", () => {
  it("DELETE /v1/keys/:id with bearer token", async () => {
    const calls = stubFetch({});
    await revokeKey("key-9", async () => "tok5");
    expect(calls[0].url).toContain("/v1/keys/key-9");
    expect(calls[0].opts.method).toBe("DELETE");
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok5");
  });
});

describe("putSlackConfig", () => {
  it("PUT /v1/projects/:id/slack with channel and token", async () => {
    const calls = stubFetch({ status: "ok" });
    await putSlackConfig("proj-3", "C123", "xoxb-secret", async () => "tok6");
    expect(calls[0].url).toContain("/v1/projects/proj-3/slack");
    expect(calls[0].opts.method).toBe("PUT");
    const body = JSON.parse(calls[0].opts.body as string) as Record<string, string>;
    expect(body.channel_id).toBe("C123");
    expect(body.bot_token).toBe("xoxb-secret");
  });
});

describe("listKeys", () => {
  it("GET /v1/projects/:id/keys with bearer token", async () => {
    const calls = stubFetch([{ id: "k1", name: "ci", prefix: "adk_" }]);
    await listKeys("proj-4", async () => "tok7");
    expect(calls[0].url).toContain("/v1/projects/proj-4/keys");
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok7");
  });
});

describe("null-token guard for new fns", () => {
  it("createProject rejects when token is null", async () => {
    const mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
    await expect(createProject("x", async () => null)).rejects.toThrow("Not authenticated");
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

// ── 401 → onUnauthorized central handling ──────────────────────────────────────

describe("handleApiError on 401", () => {
  it("calls onUnauthorized and rejects with a 401 ApiError", async () => {
    const spy = vi.spyOn(auth, "onUnauthorized").mockImplementation(() => {});
    auth401();
    await expect(fetchProjects(async () => "tok")).rejects.toMatchObject({ status: 401 });
    expect(spy).toHaveBeenCalledOnce();
  });

  it("does NOT call onUnauthorized on a non-401 error", async () => {
    const spy = vi.spyOn(auth, "onUnauthorized").mockImplementation(() => {});
    stubFetch({}, false, 500);
    await expect(fetchProjects(async () => "tok")).rejects.toBeInstanceOf(ApiError);
    expect(spy).not.toHaveBeenCalled();
  });

  it("fires for a write endpoint too (deleteProject)", async () => {
    const spy = vi.spyOn(auth, "onUnauthorized").mockImplementation(() => {});
    auth401();
    await expect(deleteProject("p1", async () => "tok")).rejects.toMatchObject({ status: 401 });
    expect(spy).toHaveBeenCalledOnce();
  });
});

// ── Slack OAuth API functions ─────────────────────────────────────────────────

describe("getSlackStatus", () => {
  it("GET /v1/projects/:id/slack with bearer token", async () => {
    const calls = stubFetch({ connected: true, channel_id: "C123", via: "oauth" });
    const result = await getSlackStatus("proj-s1", async () => "tok-status");
    expect(calls[0].url).toContain("/v1/projects/proj-s1/slack");
    expect(calls[0].opts.method).toBeUndefined(); // defaults to GET
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer tok-status",
    );
    expect(result.connected).toBe(true);
    expect(result.channel_id).toBe("C123");
    expect(result.via).toBe("oauth");
  });
});

describe("getSlackInstallUrl", () => {
  it("GET /v1/slack/install?project_id=... with bearer token, returns url", async () => {
    const calls = stubFetch({ url: "https://slack.com/oauth/v2/authorize?client_id=x" });
    const result = await getSlackInstallUrl("proj-s2", async () => "tok-install");
    expect(calls[0].url).toContain("/v1/slack/install");
    expect(calls[0].url).toContain("project_id=proj-s2");
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer tok-install",
    );
    expect(result.url).toContain("slack.com/oauth/v2/authorize");
  });
});

describe("fetchProjectStats", () => {
  it("GET /v1/projects/:id/stats returns stats shape with bearer token", async () => {
    const mockStats = {
      total_runs: 10,
      pass_rate_30: 0.8,
      failing_streak: 0,
      last_failure_at: "2026-06-01T12:00:00Z",
      drift_runs_7d: 2,
      recent: [
        { id: "r1", verdict: "pass", kind: "ci", created_at: "2026-06-01T12:00:00Z" },
      ],
    };
    const calls = stubFetch(mockStats);
    const result = await fetchProjectStats("proj-stats", async () => "tok-stats");
    expect(calls[0].url).toContain("/v1/projects/proj-stats/stats");
    expect(calls[0].opts.method).toBeUndefined(); // GET
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer tok-stats",
    );
    expect(result.total_runs).toBe(10);
    expect(result.pass_rate_30).toBe(0.8);
    expect(result.failing_streak).toBe(0);
    expect(result.drift_runs_7d).toBe(2);
    expect(result.recent).toHaveLength(1);
    expect(result.recent[0].verdict).toBe("pass");
  });

  it("handles null pass_rate_30 when no CI runs", async () => {
    const mockStats = {
      total_runs: 0,
      pass_rate_30: null,
      failing_streak: 0,
      last_failure_at: null,
      drift_runs_7d: 0,
      recent: [],
    };
    stubFetch(mockStats);
    const result = await fetchProjectStats("proj-empty", async () => "tok-empty");
    expect(result.pass_rate_30).toBeNull();
    expect(result.last_failure_at).toBeNull();
    expect(result.recent).toHaveLength(0);
  });
});

describe("disconnectSlack", () => {
  it("DELETE /v1/projects/:id/slack with bearer token", async () => {
    // Simulate 204 No Content
    const calls: { url: string; opts: RequestInit }[] = [];
    vi.stubGlobal("fetch", async (url: string, opts: RequestInit) => {
      calls.push({ url, opts });
      return { ok: true, status: 204, json: async () => undefined } as unknown as Response;
    });
    await disconnectSlack("proj-s3", async () => "tok-disconnect");
    expect(calls[0].url).toContain("/v1/projects/proj-s3/slack");
    expect(calls[0].opts.method).toBe("DELETE");
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer tok-disconnect",
    );
  });
});

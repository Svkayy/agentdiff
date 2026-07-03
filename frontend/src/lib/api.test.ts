import { describe, it, expect, vi, afterEach } from "vitest";
import {
  fetchRuns,
  fetchRun,
  fetchProjects,
  fetchMe,
  createProject,
  mintKey,
  revokeKey,
  putSlackConfig,
  listKeys,
} from "./api";

afterEach(() => vi.unstubAllGlobals());

// ── helpers ───────────────────────────────────────────────────────────────────

function stubFetch(body: unknown, ok = true) {
  const calls: { url: string; opts: RequestInit }[] = [];
  vi.stubGlobal("fetch", async (url: string, opts: RequestInit) => {
    calls.push({ url, opts });
    return { ok, json: async () => body } as Response;
  });
  return calls;
}

// ── existing tests (kept) ─────────────────────────────────────────────────────

describe("fetchRuns", () => {
  it("sends the clerk bearer token", async () => {
    const calls = stubFetch([{ id: "r1" }]);
    const runs = await fetchRuns("proj-1", async () => "jwt-abc");
    expect(runs).toEqual([{ id: "r1" }]);
    expect(calls[0].url).toContain("/v1/projects/proj-1/runs");
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer jwt-abc",
    );
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

describe("null-token guard", () => {
  it("rejects without calling fetch when token is null", async () => {
    const mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
    await expect(fetchRuns("p1", async () => null)).rejects.toThrow("Not authenticated");
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

// ── new api function tests ────────────────────────────────────────────────────

describe("fetchProjects", () => {
  it("GET /v1/projects with bearer token", async () => {
    const calls = stubFetch([{ id: "p1", name: "my-proj" }]);
    const projects = await fetchProjects(async () => "tok");
    expect(calls[0].url).toContain("/v1/projects");
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok");
    expect(projects).toEqual([{ id: "p1", name: "my-proj" }]);
  });
});

describe("fetchMe", () => {
  it("GET /v1/me with bearer token", async () => {
    const calls = stubFetch({ id: "u1", email: "x@x.com" });
    await fetchMe(async () => "tok2");
    expect(calls[0].url).toContain("/v1/me");
    expect((calls[0].opts.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok2");
  });
});

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

describe("mintKey", () => {
  it("POST /v1/projects/:id/keys", async () => {
    const calls = stubFetch({ id: "k1", key: "agd_secret", prefix: "agd_" });
    const result = await mintKey("proj-5", async () => "tok4");
    expect(calls[0].url).toContain("/v1/projects/proj-5/keys");
    expect(calls[0].opts.method).toBe("POST");
    expect(result).toMatchObject({ prefix: "agd_" });
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
    const calls = stubFetch([{ id: "k1", prefix: "agd_" }]);
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

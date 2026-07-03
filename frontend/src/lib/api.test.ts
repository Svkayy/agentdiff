import { describe, it, expect, vi, afterEach } from "vitest";
import { fetchRuns, fetchRun } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("fetchRuns", () => {
  it("sends the clerk bearer token", async () => {
    const calls: any[] = [];
    vi.stubGlobal("fetch", async (url: string, opts: any) => {
      calls.push({ url, opts });
      return { ok: true, json: async () => [{ id: "r1" }] } as any;
    });
    const getToken = async () => "jwt-abc";
    const runs = await fetchRuns("proj-1", getToken);
    expect(runs).toEqual([{ id: "r1" }]);
    expect(calls[0].url).toContain("/v1/projects/proj-1/runs");
    expect(calls[0].opts.headers.Authorization).toBe("Bearer jwt-abc");
  });
});

describe("fetchRun", () => {
  it("fetches the correct run URL with bearer token", async () => {
    const calls: any[] = [];
    const stubbed = { id: "run-1", status: "done" };
    vi.stubGlobal("fetch", async (url: string, opts: any) => {
      calls.push({ url, opts });
      return { ok: true, json: async () => stubbed } as any;
    });
    const result = await fetchRun("run-1", async () => "jwt-xyz");
    expect(calls[0].url).toContain("/v1/runs/run-1");
    expect(calls[0].opts.headers.Authorization).toBe("Bearer jwt-xyz");
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

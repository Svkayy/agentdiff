import { describe, it, expect, vi } from "vitest";
import { fetchRuns } from "./api";

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

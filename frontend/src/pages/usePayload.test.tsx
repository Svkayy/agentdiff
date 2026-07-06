// @vitest-environment jsdom
// Run-detail payload loading: success, terminal-404 fallback ("Report data is
// unavailable"), in-progress polling, poll-attempt cap, and generic errors.
// The server-side 404 semantics are covered in tests/server/test_payload.py —
// this covers the client hook that consumes them.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

vi.mock("@/lib/api", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...orig,
    fetchRunPayload: vi.fn(),
    fetchRun: vi.fn(),
  };
});

import { fetchRunPayload, ApiError } from "@/lib/api";
import { usePayload } from "./RunDetailPage";

const fetchPayloadMock = vi.mocked(fetchRunPayload);
const getToken = async () => "test-token";

beforeEach(() => {
  fetchPayloadMock.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("usePayload", () => {
  it("stores the payload on success", async () => {
    fetchPayloadMock.mockResolvedValue({ schema_version: 1 });
    const { result } = renderHook(() =>
      usePayload("run-1", "done", getToken),
    );
    await waitFor(() => expect(result.current.payload).not.toBeNull());
    expect(result.current.payloadError).toBeNull();
    expect(result.current.payloadPending).toBe(false);
  });

  it("reports 'Report data is unavailable' for a terminal run whose payload 404s", async () => {
    fetchPayloadMock.mockRejectedValue(new ApiError(404, "API 404"));
    const { result } = renderHook(() =>
      usePayload("run-1", "done", getToken),
    );
    await waitFor(() =>
      expect(result.current.payloadError).toBe(
        "Report data is unavailable for this run.",
      ),
    );
    // Terminal state: no polling scheduled.
    expect(fetchPayloadMock).toHaveBeenCalledTimes(1);
    expect(result.current.payloadPending).toBe(false);
  });

  it("polls while the run is in progress and resolves when the payload appears", async () => {
    vi.useFakeTimers();
    fetchPayloadMock
      .mockRejectedValueOnce(new ApiError(404, "API 404"))
      .mockResolvedValueOnce({ schema_version: 1 });

    const { result } = renderHook(() =>
      usePayload("run-1", "processing", getToken),
    );

    // First attempt 404s → pending, a 5s retry is scheduled.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.payloadPending).toBe(true);
    expect(result.current.payloadError).toBeNull();

    // Advance past the poll interval — second attempt succeeds.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(result.current.payload).not.toBeNull();
    expect(result.current.payloadPending).toBe(false);
    expect(fetchPayloadMock).toHaveBeenCalledTimes(2);
  });

  it("gives up after the poll-attempt cap instead of polling forever", async () => {
    vi.useFakeTimers();
    fetchPayloadMock.mockRejectedValue(new ApiError(404, "API 404"));

    const { result } = renderHook(() =>
      usePayload("run-1", "pending", getToken),
    );

    // Drain 200 poll attempts (MAX_POLL_ATTEMPTS) at 5s each.
    await act(async () => {
      for (let i = 0; i < 201; i++) {
        await vi.advanceTimersByTimeAsync(5000);
      }
    });

    expect(result.current.payloadError).toBe(
      "Report data is unavailable for this run.",
    );
    expect(result.current.payloadPending).toBe(false);
  });

  it("surfaces non-404 errors directly without polling", async () => {
    fetchPayloadMock.mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() =>
      usePayload("run-1", "processing", getToken),
    );
    await waitFor(() => expect(result.current.payloadError).toBe("boom"));
    expect(fetchPayloadMock).toHaveBeenCalledTimes(1);
  });
});

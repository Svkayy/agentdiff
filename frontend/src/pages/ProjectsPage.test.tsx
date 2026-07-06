// @vitest-environment jsdom
// Projects list user flows: fetch-error banner + Retry recovery, and the
// empty state. The API layer is tested in lib/api.test.ts — this covers the
// component behavior on top of it.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

vi.mock("@clerk/clerk-react", () => {
  // getToken must be referentially stable across renders (as Clerk's real
  // useAuth is) — a fresh function per render would re-fire the page's
  // load effect on every state change.
  const getToken = async () => "test-token";
  return { useAuth: () => ({ getToken }) };
});

vi.mock("@/lib/api", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...orig,
    fetchProjects: vi.fn(),
    createProject: vi.fn(),
  };
});

import { fetchProjects } from "@/lib/api";
import { ProjectsPage } from "./ProjectsPage";

const fetchProjectsMock = vi.mocked(fetchProjects);

function renderPage() {
  return render(
    <MemoryRouter>
      <ProjectsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  fetchProjectsMock.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("ProjectsPage", () => {
  it("shows the error banner when the fetch fails, and recovers via Retry", async () => {
    fetchProjectsMock.mockRejectedValue(new Error("Failed to fetch"));
    renderPage();

    expect(await screen.findByText("Failed to fetch", {}, { timeout: 5000 })).toBeTruthy();
    const retry = screen.getByRole("button", { name: /retry/i });

    fetchProjectsMock.mockResolvedValue({
      items: [{ id: "p1", name: "Alpha" }],
      total: 1,
    });
    await userEvent.click(retry);

    expect(await screen.findByText("Alpha", {}, { timeout: 5000 })).toBeTruthy();
    expect(screen.queryByText("Failed to fetch")).toBeNull();
  });

  it("shows the empty state when there are no projects", async () => {
    fetchProjectsMock.mockResolvedValue({
      items: [],
      total: 0,
    });
    renderPage();

    expect(
      await screen.findByText(/create your first project/i, {}, { timeout: 5000 }),
    ).toBeTruthy();
  });

  it("renders a card per project", async () => {
    fetchProjectsMock.mockResolvedValue({
      items: [
        { id: "p1", name: "Alpha" },
        { id: "p2", name: "Beta" },
      ],
      total: 2,
    });
    renderPage();

    expect(await screen.findByText("Alpha", {}, { timeout: 5000 })).toBeTruthy();
    expect(screen.getByText("Beta")).toBeTruthy();
  });
});

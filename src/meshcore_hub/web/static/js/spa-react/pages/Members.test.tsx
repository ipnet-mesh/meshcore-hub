import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Members } from "@/pages/Members";
import { renderWithProviders } from "@/test/renderWithProviders";
import * as api from "@/utils/api";

const PROFILES = {
  items: [
    { id: "1", name: "Alice", roles: ["operator"], callsign: "AB1" },
    { id: "2", name: "Bob", roles: ["member"] },
    { id: "3", name: "TestUser", roles: ["test"] },
  ],
};

function mockProfiles(items = PROFILES) {
  vi.spyOn(api, "apiGet").mockResolvedValue(items);
}

describe("Members", () => {
  it("shows a loading spinner before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Members />);
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders operators and members excluding test profiles", async () => {
    mockProfiles();
    renderWithProviders(<Members />);
    await waitFor(() => {
      expect(screen.getByText("Alice")).toBeInTheDocument();
    });
    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.queryByText("TestUser")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "entities.members" }).querySelector("svg"),
    ).not.toBeNull();
  });

  it("shows an empty state when no visible profiles exist", async () => {
    mockProfiles({
      items: [{ id: "9", name: "Hidden", roles: ["test"] }],
    });
    renderWithProviders(<Members />);
    await waitFor(() => {
      expect(screen.getByText("members_page.empty_state")).toBeInTheDocument();
    });
  });

  it("shows an error alert on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("fetch failed"));
    renderWithProviders(<Members />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("fetch failed");
    });
  });
});

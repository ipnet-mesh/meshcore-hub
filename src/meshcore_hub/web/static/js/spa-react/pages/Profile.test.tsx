import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Profile } from "@/pages/Profile";
import { renderWithProviders } from "@/test/renderWithProviders";
import { makeConfig } from "@/test/makeConfig";
import * as api from "@/utils/api";

const PROFILE_DATA = {
  id: "p1",
  user_id: "user-123",
  name: "Jane Operator",
  callsign: "AB1CDE",
  description: "Mesh enthusiast",
  url: "https://example.com",
  roles: ["operator"],
  created_at: "2024-01-01T00:00:00Z",
  nodes: [],
};

describe("Profile (public view)", () => {
  it("shows a loading spinner before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Profile />, {
      route: "/profile/p1",
      routePath: "/profile/:id",
    });
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders profile fields after data resolves", async () => {
    vi.spyOn(api, "apiGet").mockResolvedValue(PROFILE_DATA);
    renderWithProviders(<Profile />, {
      route: "/profile/p1",
      routePath: "/profile/:id",
    });
    await waitFor(() => {
      expect(screen.getAllByText("Jane Operator").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText("AB1CDE").length).toBeGreaterThanOrEqual(1);
  });

  it("shows an error alert on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("profile error"));
    renderWithProviders(<Profile />, {
      route: "/profile/p1",
      routePath: "/profile/:id",
    });
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("profile error");
    });
  });
});

describe("Profile (own view)", () => {
  it("shows a login prompt when OIDC is disabled", async () => {
    renderWithProviders(<Profile />, { route: "/profile" });
    await waitFor(() => {
      expect(screen.getByText("auth.login")).toBeInTheDocument();
    });
  });

  it("renders the edit form for a logged-in user", async () => {
    vi.spyOn(api, "apiGet").mockResolvedValue(PROFILE_DATA);
    renderWithProviders(<Profile />, {
      route: "/profile",
      config: makeConfig({
        oidc_enabled: true,
        user: { sub: "user-123", name: "Jane" },
      }),
    });
    await waitFor(() => {
      expect(screen.getByDisplayValue("Jane Operator")).toBeInTheDocument();
    });
  });
});

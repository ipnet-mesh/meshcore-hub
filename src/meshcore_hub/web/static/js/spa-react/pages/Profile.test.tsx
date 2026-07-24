import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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

describe("Profile (admin edit)", () => {
  afterEach(() => {
    window.__APP_CONFIG__ = makeConfig();
  });

  function setAdminConfig() {
    const config = makeConfig({
      oidc_enabled: true,
      user: { sub: "admin-user", name: "Admin" },
      roles: ["admin"],
      role_names: { admin: "admin", operator: "operator", member: "member" },
    });
    window.__APP_CONFIG__ = config;
    return config;
  }

  function setMemberConfig() {
    const config = makeConfig({
      oidc_enabled: true,
      user: { sub: "other-user", name: "Member" },
      roles: ["member"],
      role_names: { admin: "admin", operator: "operator", member: "member" },
    });
    window.__APP_CONFIG__ = config;
    return config;
  }

  it("admin sees edit button on another user's profile", async () => {
    vi.spyOn(api, "apiGet").mockResolvedValue(PROFILE_DATA);
    const config = setAdminConfig();
    renderWithProviders(<Profile />, {
      route: "/profile/p1",
      routePath: "/profile/:id",
      config,
    });
    await waitFor(() => {
      expect(screen.getByTestId("profile-admin-edit")).toBeInTheDocument();
    });
  });

  it("non-admin does not see edit button on another user's profile", async () => {
    vi.spyOn(api, "apiGet").mockResolvedValue(PROFILE_DATA);
    const config = setMemberConfig();
    renderWithProviders(<Profile />, {
      route: "/profile/p1",
      routePath: "/profile/:id",
      config,
    });
    await waitFor(() => {
      expect(screen.getAllByText("Jane Operator").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.queryByTestId("profile-admin-edit")).toBeNull();
  });

  it("owner sees edit link, not admin edit button", async () => {
    vi.spyOn(api, "apiGet").mockResolvedValue(PROFILE_DATA);
    const config = makeConfig({
      oidc_enabled: true,
      user: { sub: "user-123", name: "Jane" },
      roles: ["admin"],
      role_names: { admin: "admin", operator: "operator", member: "member" },
    });
    window.__APP_CONFIG__ = config;
    renderWithProviders(<Profile />, {
      route: "/profile/p1",
      routePath: "/profile/:id",
      config,
    });
    await waitFor(() => {
      expect(screen.getAllByText("Jane Operator").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.queryByTestId("profile-admin-edit")).toBeNull();
  });

  it("admin edit form submits to correct endpoint", async () => {
    vi.spyOn(api, "apiGet").mockResolvedValue(PROFILE_DATA);
    const apiPutSpy = vi.spyOn(api, "apiPut").mockResolvedValue(undefined);
    const config = setAdminConfig();
    renderWithProviders(<Profile />, {
      route: "/profile/p1",
      routePath: "/profile/:id",
      config,
    });
    await waitFor(() => {
      expect(screen.getByTestId("profile-admin-edit")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("profile-admin-edit"));

    const nameInput = await screen.findByTestId("profile-name");
    fireEvent.change(nameInput, { target: { value: "Admin Set Name" } });
    fireEvent.click(screen.getByTestId("profile-save"));

    await waitFor(() => {
      expect(apiPutSpy).toHaveBeenCalledWith("/api/v1/user/profile/p1", {
        name: "Admin Set Name",
        callsign: "AB1CDE",
        description: "Mesh enthusiast",
        url: "https://example.com",
      });
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

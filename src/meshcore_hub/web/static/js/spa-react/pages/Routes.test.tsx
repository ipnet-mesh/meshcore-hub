import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/charts/Charts", () => ({
  ActivityChart: () => null,
  TrendLineChart: () => null,
  StackedBarChart: () => null,
  RoutesTrendChart: () => null,
  RouteDetailStrip: () => null,
}));

import { RoutesPage as Routes } from "@/pages/Routes";
import { renderWithProviders } from "@/test/renderWithProviders";
import { makeConfig } from "@/test/makeConfig";
import * as api from "@/utils/api";

const ROUTES = {
  items: [
    {
      id: "r1",
      from_label: "NodeA",
      to_label: "NodeB",
      description: "Primary route",
      visibility: "community",
      enabled: true,
      reversible: false,
      match_width: 60,
      window_hours: 24,
      quality_avg: "clear",
      route_result: { quality: "clear", state: "healthy" },
      route_nodes: [],
      route_observers: [],
    },
  ],
};

const ROUTE_DETAIL = {
  id: "r1",
  from_label: "NodeA",
  to_label: "NodeB",
  recent_matches: [],
};

const ROUTE_HISTORY = {
  buckets: [],
};

function mockRoutesApi() {
  vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
    if (path === "/api/v1/routes") return ROUTES;
    if (path.match(/\/api\/v1\/routes\/[^/]+$/)) return ROUTE_DETAIL;
    if (path.includes("/history")) return ROUTE_HISTORY;
    throw new Error(`Unexpected: ${path}`);
  });
}

describe("Routes", () => {
  it("shows a loading state before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Routes />);
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders route cards after data resolves", async () => {
    mockRoutesApi();
    renderWithProviders(<Routes />);
    await waitFor(() => {
      expect(screen.getAllByText("NodeA").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows an error on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("routes error"));
    renderWithProviders(<Routes />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("routes error");
    });
  });
});

describe("Routes role-gated management", () => {
  // hasRole() reads window.__APP_CONFIG__ directly (not the React context),
  // so we must assign the global to simulate an authenticated session.
  function setRoles(roles: string[]) {
    window.__APP_CONFIG__ = makeConfig({
      oidc_enabled: true,
      roles,
      role_names: { admin: "admin", operator: "operator", member: "member" },
    });
  }

  afterEach(() => {
    window.__APP_CONFIG__ = makeConfig();
  });

  it("hides the add button from an unprivileged user", async () => {
    setRoles(["member"]);
    mockRoutesApi();
    renderWithProviders(<Routes />);
    await waitFor(() => {
      expect(screen.getAllByText("NodeA").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.queryByTestId("add-route")).toBeNull();
  });

  it("shows the add button to an operator", async () => {
    setRoles(["operator"]);
    mockRoutesApi();
    renderWithProviders(<Routes />);
    expect(await screen.findByTestId("add-route")).toBeInTheDocument();
  });

  it("offers all visibility tiers to an admin", async () => {
    setRoles(["admin"]);
    mockRoutesApi();
    renderWithProviders(<Routes />);
    fireEvent.click(await screen.findByTestId("add-route"));
    const select = (await screen.findByTestId(
      "route-visibility",
    )) as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(["community", "member", "operator", "admin"]);
  });

  it("hides the admin tier from an operator", async () => {
    setRoles(["operator"]);
    mockRoutesApi();
    renderWithProviders(<Routes />);
    fireEvent.click(await screen.findByTestId("add-route"));
    const select = (await screen.findByTestId(
      "route-visibility",
    )) as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(["community", "member", "operator"]);
    expect(values).not.toContain("admin");
  });
});

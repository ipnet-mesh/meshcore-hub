import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/charts/Charts", () => ({
  ActivityChart: () => null,
  TrendLineChart: () => null,
  StackedBarChart: () => null,
  RoutesTrendChart: () => null,
  RouteDetailStrip: () => null,
}));

import { RoutesPage as Routes } from "@/pages/Routes";
import { renderWithProviders } from "@/test/renderWithProviders";
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

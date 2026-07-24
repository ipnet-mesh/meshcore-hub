import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/charts/Charts", () => ({
  ActivityChart: () => null,
  TrendLineChart: () => null,
  StackedBarChart: () => null,
  RoutesTrendChart: () => null,
  RouteDetailStrip: () => null,
}));

import { DashboardPage as Dashboard } from "@/pages/Dashboard";
import { renderWithProviders } from "@/test/renderWithProviders";
import { makeConfig } from "@/test/makeConfig";
import * as api from "@/utils/api";

const STATS = {
  node_count: 10,
  message_count: 50,
  packet_count: 200,
  channel_count: 3,
  observer_count: 4,
  route_count: 1,
};

function mockDashboardApi() {
  vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
    if (path.includes("/dashboard/stats")) return STATS;
    if (path.includes("/dashboard/")) return { data: [] };
    if (path.includes("/api/v1/channels")) return { items: [] };
    throw new Error(`Unexpected: ${path}`);
  });
}

describe("Dashboard", () => {
  it("shows a loading state before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Dashboard />);
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders dashboard content after data resolves", async () => {
    mockDashboardApi();
    renderWithProviders(<Dashboard />);
    await waitFor(() => {
      expect(document.querySelector(".loading-spinner")).toBeNull();
    });
    expect(
      screen.getByRole("heading", { name: "entities.dashboard" }).querySelector("svg"),
    ).not.toBeNull();
  });

  it("shows an error on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("dash error"));
    renderWithProviders(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("dash error");
    });
  });
});

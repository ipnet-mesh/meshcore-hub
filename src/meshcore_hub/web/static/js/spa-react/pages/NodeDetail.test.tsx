import { screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="mock-map">{children}</div>
  ),
  TileLayer: () => null,
  Marker: () => null,
  Popup: () => null,
  useMap: () => ({ fitBounds: () => {} }),
}));

vi.mock("leaflet", () => ({
  divIcon: () => ({}),
  latLngBounds: () => ({}),
  point: () => ({}),
}));

vi.mock("@/components/MeshQrCode", () => ({
  MeshQrCode: () => <div data-testid="mock-qr" />,
}));

import { NodeDetailPage as NodeDetail } from "@/pages/NodeDetail";
import { renderWithProviders } from "@/test/renderWithProviders";
import * as api from "@/utils/api";

const KEY = "a".repeat(64);
const NODE = {
  public_key: KEY,
  name: "DetailNode",
  adv_type: "chat",
  last_seen: "2024-01-01T00:00:00Z",
  tags: [],
};

function mockNodeDetailApi() {
  vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
    if (path.includes(`/api/v1/nodes/${KEY}`)) return NODE;
    if (path.includes("/api/v1/advertisements")) return { items: [], total: 0 };
    throw new Error(`Unexpected: ${path}`);
  });
}

describe("NodeDetail", () => {
  it("shows a loading state before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<NodeDetail />, {
      route: `/nodes/${KEY}`,
      routePath: "/nodes/:publicKey",
    });
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders node detail after data resolves", async () => {
    mockNodeDetailApi();
    renderWithProviders(<NodeDetail />, {
      route: `/nodes/${KEY}`,
      routePath: "/nodes/:publicKey",
    });
    await waitFor(() => {
      expect(document.querySelector(".loading-spinner")).toBeNull();
    });
  });

  it("shows an error on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("node error"));
    renderWithProviders(<NodeDetail />, {
      route: `/nodes/${KEY}`,
      routePath: "/nodes/:publicKey",
    });
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("node error");
    });
  });
});

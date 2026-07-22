import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RouteTypeBadge } from "@/components/RouteTypeBadge";

describe("RouteTypeBadge", () => {
  it("renders nothing for null", () => {
    const { container } = render(<RouteTypeBadge routeType={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders Flood badge for flood", () => {
    render(<RouteTypeBadge routeType="flood" />);
    expect(screen.getByText("Flood")).toHaveClass("badge-info");
  });

  it("renders Relay badge for transport_flood", () => {
    render(<RouteTypeBadge routeType="transport_flood" />);
    expect(screen.getByText("Relay")).toHaveClass("badge-info");
  });

  it("renders Zero-hop for direct", () => {
    render(<RouteTypeBadge routeType="direct" />);
    expect(screen.getByText("Zero-hop")).toHaveClass("badge-success");
  });

  it("renders Direct relay for transport_direct", () => {
    render(<RouteTypeBadge routeType="transport_direct" />);
    expect(screen.getByText("Direct relay")).toHaveClass("badge-success");
  });

  it("renders nothing for an unknown type", () => {
    const { container } = render(<RouteTypeBadge routeType="weird" />);
    expect(container.firstChild).toBeNull();
  });
});

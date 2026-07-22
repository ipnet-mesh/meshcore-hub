import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatCard } from "@/components/StatCard";

describe("StatCard", () => {
  it("renders title, formatted value, and description", () => {
    render(
      <StatCard
        icon="star"
        color="#f00"
        title="Nodes"
        value={1234}
        description="active"
      />,
    );
    expect(screen.getByText("Nodes")).toHaveClass("stat-title");
    expect(screen.getByText("1,234")).toHaveClass("stat-value");
    expect(screen.getByText("active")).toHaveClass("stat-desc");
  });

  it("omits description when not provided", () => {
    const { container } = render(
      <StatCard icon="star" color="#f00" title="X" value={5} />,
    );
    expect(container.querySelector(".stat-desc")).toBeNull();
  });

  it("applies the panel color as a CSS variable", () => {
    const { container } = render(
      <StatCard icon="star" color="#abc" title="X" value={1} />,
    );
    const panel = container.querySelector(".stat") as HTMLElement;
    expect(panel.style.getPropertyValue("--panel-color")).toBe("#abc");
  });
});

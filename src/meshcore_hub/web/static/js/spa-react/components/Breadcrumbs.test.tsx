import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { Breadcrumbs, type Crumb } from "@/components/Breadcrumbs";

function renderCrumbs(items: Crumb[]) {
  return render(
    <MemoryRouter>
      <Breadcrumbs items={items} />
    </MemoryRouter>,
  );
}

const items: Crumb[] = [
  { label: "Home", to: "/" },
  { label: "Nodes", to: "/nodes" },
  { label: "AB1234" },
];

describe("Breadcrumbs", () => {
  it("renders a nav landmark labelled Breadcrumb", () => {
    renderCrumbs(items);
    expect(
      screen.getByRole("navigation", { name: "Breadcrumb" }),
    ).toBeInTheDocument();
  });

  it("links non-final crumbs to their targets", () => {
    renderCrumbs(items);
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.getByRole("link", { name: "Nodes" })).toHaveAttribute(
      "href",
      "/nodes",
    );
  });

  it("renders the final crumb as plain text with aria-current=page", () => {
    renderCrumbs(items);
    expect(
      screen.queryByRole("link", { name: "AB1234" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("AB1234").closest("li")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("renders a crumb without a target as plain text even mid-trail", () => {
    renderCrumbs([
      { label: "Home", to: "/" },
      { label: "Static" },
      { label: "Leaf" },
    ]);
    expect(
      screen.queryByRole("link", { name: "Static" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Static")).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MobileNav } from "@/components/MobileNav";
import { makeConfig } from "@/test/makeConfig";
import { renderWithProviders } from "@/test/renderWithProviders";

function renderMobileNav(config = makeConfig()) {
  return renderWithProviders(<MobileNav />, { config });
}

describe("MobileNav", () => {
  it("renders nav items for enabled features", () => {
    renderMobileNav();
    const links = screen.getAllByTestId("nav-link");
    expect(links.length).toBeGreaterThan(0);
    expect(links[0]).toHaveAttribute("data-nav-href", "/");
  });

  it("hides links for disabled features", () => {
    renderMobileNav(makeConfig({ features: { map: false, members: false } }));
    const hrefs = screen
      .getAllByTestId("nav-link")
      .map((l) => l.getAttribute("data-nav-href"));
    expect(hrefs).not.toContain("/map");
    expect(hrefs).not.toContain("/members");
  });
});

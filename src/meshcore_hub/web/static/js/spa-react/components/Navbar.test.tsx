import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { AppConfigProvider } from "@/context/AppConfigContext";
import { Navbar } from "@/components/Navbar";
import { makeConfig } from "@/test/makeConfig";
import type { AppConfig } from "@/types/config";

function renderNavbar(config: AppConfig) {
  return render(
    <AppConfigProvider config={config}>
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    </AppConfigProvider>,
  );
}

// Each nav label renders twice (desktop menu + mobile dropdown).
const labelCount = (label: string) => screen.queryAllByText(label).length;

describe("Navbar feature gating", () => {
  it("renders all feature links when every feature is enabled", () => {
    renderNavbar(makeConfig());
    expect(labelCount("entities.home")).toBeGreaterThan(0);
    expect(labelCount("entities.dashboard")).toBeGreaterThan(0);
    expect(labelCount("entities.nodes")).toBeGreaterThan(0);
    expect(labelCount("entities.messages")).toBeGreaterThan(0);
    expect(labelCount("entities.map")).toBeGreaterThan(0);
  });

  it("hides links for disabled features", () => {
    renderNavbar(
      makeConfig({
        features: { dashboard: false, nodes: false, map: false },
      }),
    );
    expect(labelCount("entities.dashboard")).toBe(0);
    expect(labelCount("entities.nodes")).toBe(0);
    expect(labelCount("entities.map")).toBe(0);
    // Still-enabled features remain
    expect(labelCount("entities.messages")).toBeGreaterThan(0);
    expect(labelCount("entities.home")).toBeGreaterThan(0);
  });

  it("shows only Home when all features are off (maintenance)", () => {
    renderNavbar(
      makeConfig({
        system_maintenance: true,
        features: {
          dashboard: false,
          nodes: false,
          advertisements: false,
          routes: false,
          channels: false,
          messages: false,
          packets: false,
          map: false,
          members: false,
          pages: false,
        },
      }),
    );
    expect(labelCount("entities.home")).toBeGreaterThan(0);
    expect(labelCount("entities.dashboard")).toBe(0);
    expect(labelCount("entities.nodes")).toBe(0);
    expect(labelCount("entities.messages")).toBe(0);
  });

  it("renders custom pages when the pages feature is enabled", () => {
    renderNavbar(
      makeConfig({
        custom_pages: [
          { slug: "about", title: "About Us", url: "/pages/about", menu_order: 1 },
        ],
      }),
    );
    expect(labelCount("About Us")).toBeGreaterThan(0);
  });

  it("hides custom pages when the pages feature is disabled", () => {
    renderNavbar(
      makeConfig({
        features: { pages: false },
        custom_pages: [
          { slug: "about", title: "About Us", url: "/pages/about", menu_order: 1 },
        ],
      }),
    );
    expect(labelCount("About Us")).toBe(0);
  });
});

describe("Navbar auth gating", () => {
  it("shows the login button when OIDC is enabled and not in maintenance", () => {
    renderNavbar(makeConfig({ oidc_enabled: true }));
    expect(labelCount("auth.login")).toBeGreaterThan(0);
  });

  it("hides auth when OIDC is disabled", () => {
    renderNavbar(makeConfig({ oidc_enabled: false }));
    expect(labelCount("auth.login")).toBe(0);
  });

  it("hides auth in maintenance mode even when OIDC is enabled", () => {
    renderNavbar(
      makeConfig({ oidc_enabled: true, system_maintenance: true }),
    );
    expect(labelCount("auth.login")).toBe(0);
  });
});

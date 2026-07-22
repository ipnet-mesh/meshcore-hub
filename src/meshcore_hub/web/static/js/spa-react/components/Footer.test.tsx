import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppConfigProvider } from "@/context/AppConfigContext";
import { Footer } from "@/components/Footer";
import { makeConfig } from "@/test/makeConfig";
import type { AppConfig } from "@/types/config";

function renderFooter(config: AppConfig) {
  return render(
    <AppConfigProvider config={config}>
      <Footer />
    </AppConfigProvider>,
  );
}

describe("Footer", () => {
  it("renders the network name and version", () => {
    renderFooter(makeConfig({ network_name: "HamNet", version: "2.3.4" }));
    expect(screen.getByText("HamNet")).toBeInTheDocument();
    expect(screen.getByText(/2\.3\.4/)).toBeInTheDocument();
  });

  it("renders city and country when both are set", () => {
    renderFooter(
      makeConfig({ network_name: "HamNet", network_city: "Berlin", network_country: "DE" }),
    );
    expect(screen.getByText("HamNet | Berlin, DE")).toBeInTheDocument();
  });

  it("omits the locale segment when city or country is missing", () => {
    renderFooter(makeConfig({ network_name: "HamNet", network_city: "Berlin" }));
    expect(screen.getByText("HamNet")).toBeInTheDocument();
    expect(screen.queryByText(/Berlin/)).not.toBeInTheDocument();
  });

  it("renders contact links when provided", () => {
    renderFooter(
      makeConfig({
        network_contact_email: "op@example.com",
        network_contact_discord: "https://discord.gg/x",
        network_contact_github: "https://github.com/x",
        network_contact_youtube: "https://youtube.com/@x",
      }),
    );
    expect(screen.getByText("op@example.com")).toHaveAttribute("href", "mailto:op@example.com");
    expect(screen.getByText("links.discord")).toHaveAttribute("href", "https://discord.gg/x");
    expect(screen.getByText("links.youtube")).toHaveAttribute("href", "https://youtube.com/@x");
    // "links.github" appears twice (MeshCore project link + network contact link) — pick by href
    expect(screen.getAllByText("links.github").length).toBe(2);
    expect(
      screen.getByText("links.github", { selector: 'a[href="https://github.com/x"]' }),
    ).toBeInTheDocument();
  });

  it("omits all contact links when none are set", () => {
    const { container } = renderFooter(makeConfig());
    const paragraphs = container.querySelectorAll("p");
    // No contact link hrefs anywhere in the footer
    expect(container.querySelector('a[href^="mailto:"]')).toBeNull();
    expect(container.querySelector('a[href*="discord"]')).toBeNull();
    expect(paragraphs.length).toBeGreaterThanOrEqual(1);
  });

  it("renders partial contact links without stray separators", () => {
    renderFooter(
      makeConfig({
        network_contact_email: "op@example.com",
        network_contact_youtube: "https://youtube.com/@x",
      }),
    );
    expect(screen.getByText("op@example.com")).toBeInTheDocument();
    expect(screen.getByText("links.youtube")).toHaveAttribute(
      "href",
      "https://youtube.com/@x",
    );
    expect(screen.queryByText("links.discord")).not.toBeInTheDocument();
    // Only the MeshCore project github link — no contact github link
    expect(screen.getAllByText("links.github").length).toBe(1);
  });

  it("falls back to 'MeshCore Network' when network_name is empty", () => {
    renderFooter(makeConfig({ network_name: "" }));
    expect(screen.getByText("MeshCore Network")).toBeInTheDocument();
  });

  it("renders the MeshCore Hub attribution link", () => {
    renderFooter(makeConfig());
    expect(screen.getByText("MeshCore Hub").closest("a")).toHaveAttribute(
      "href",
      "https://github.com/ipnet-mesh/meshcore-hub",
    );
  });
});

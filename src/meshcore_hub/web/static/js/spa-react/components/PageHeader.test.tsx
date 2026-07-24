import { render, screen } from "@testing-library/react";
import type { ComponentType, ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { AppConfigProvider } from "@/context/AppConfigContext";
import { PageHeader } from "@/components/PageHeader";
import { IconNodes } from "@/components/icons";
import { makeConfig } from "@/test/makeConfig";
import type { AppConfig } from "@/types/config";

function renderHeader(
  config: AppConfig = makeConfig(),
  children?: ReactNode,
  icon?: ComponentType<{ className?: string }>,
) {
  return render(
    <AppConfigProvider config={config}>
      <PageHeader title="Nodes" icon={icon}>
        {children}
      </PageHeader>
    </AppConfigProvider>,
  );
}

describe("PageHeader", () => {
  it("renders the title", () => {
    renderHeader();
    expect(
      screen.getByRole("heading", { name: "Nodes" }),
    ).toBeInTheDocument();
  });

  it("hides the timezone indicator for UTC", () => {
    const { container } = renderHeader(makeConfig({ timezone: "UTC" }));
    expect(container.textContent).not.toContain("UTC");
  });

  it("shows a non-UTC timezone", () => {
    renderHeader(makeConfig({ timezone: "America/New_York" }));
    expect(screen.getByText("America/New_York")).toBeInTheDocument();
  });

  it("renders right-side children alongside the timezone", () => {
    renderHeader(
      makeConfig({ timezone: "EST" }),
      <span>extra badge</span>,
    );
    expect(screen.getByText("EST")).toBeInTheDocument();
    expect(screen.getByText("extra badge")).toBeInTheDocument();
  });

  it("renders the icon inside the heading when provided", () => {
    renderHeader(makeConfig(), undefined, IconNodes);
    const svg = screen
      .getByRole("heading", { name: "Nodes" })
      .querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("class")).toContain("h-8");
    expect(svg?.getAttribute("class")).toContain("w-8");
  });

  it("renders no icon when omitted", () => {
    renderHeader();
    expect(
      screen.getByRole("heading", { name: "Nodes" }).querySelector("svg"),
    ).toBeNull();
  });
});

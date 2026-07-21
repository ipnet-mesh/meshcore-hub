import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { AppConfigProvider } from "@/context/AppConfigContext";
import { PageHeader } from "@/components/PageHeader";
import { makeConfig } from "@/test/makeConfig";
import type { AppConfig } from "@/types/config";

function renderHeader(config: AppConfig = makeConfig(), children?: ReactNode) {
  return render(
    <AppConfigProvider config={config}>
      <PageHeader title="Nodes">{children}</PageHeader>
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
});

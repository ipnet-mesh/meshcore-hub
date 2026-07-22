import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { AppConfigProvider } from "@/context/AppConfigContext";
import { Announcements } from "@/components/Announcements";
import { makeConfig } from "@/test/makeConfig";
import type { AppConfig } from "@/types/config";

function renderAnnouncements(config: AppConfig) {
  return render(
    <AppConfigProvider config={config}>
      <Announcements />
    </AppConfigProvider>,
  );
}

beforeEach(() => {
  sessionStorage.clear();
});

describe("Announcements", () => {
  it("renders nothing when there are no announcements", () => {
    const { container } = renderAnnouncements(makeConfig());
    expect(container.firstChild).toBeNull();
  });

  it("renders the system banner content rendered from markdown", () => {
    const { container } = renderAnnouncements(
      makeConfig({ system_announcement: "**Outage** at 22:00" }),
    );
    expect(container.querySelector("#system-banner")).not.toBeNull();
    expect(screen.getByText("Outage").tagName).toBe("STRONG");
  });

  it("renders the network banner with a dismiss button", () => {
    const { container } = renderAnnouncements(
      makeConfig({ network_announcement: "Notice" }),
    );
    expect(container.querySelector("#flash-banner")).not.toBeNull();
    expect(screen.getByLabelText("Dismiss")).toBeInTheDocument();
  });

  it("renders the network banner content rendered from markdown", () => {
    const { container } = renderAnnouncements(
      makeConfig({ network_announcement: "**Maintenance** done" }),
    );
    const banner = container.querySelector("#flash-banner");
    expect(banner).not.toBeNull();
    expect(screen.getByText("Maintenance").tagName).toBe("STRONG");
  });

  it("does not render a dismiss control on the system banner", () => {
    const { container } = renderAnnouncements(
      makeConfig({ system_announcement: "Heads up" }),
    );
    const banner = container.querySelector("#system-banner");
    expect(banner).not.toBeNull();
    expect(banner!.querySelector("button")).toBeNull();
  });

  it("renders the system banner above the network banner", () => {
    const { container } = renderAnnouncements(
      makeConfig({
        system_announcement: "System notice",
        network_announcement: "Network notice",
      }),
    );
    const system = container.querySelector("#system-banner");
    const network = container.querySelector("#flash-banner");
    expect(system).not.toBeNull();
    expect(network).not.toBeNull();
    // network follows system in document order
    expect(
      system!.compareDocumentPosition(network!) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("dismisses the network banner and persists to sessionStorage", () => {
    const { container } = renderAnnouncements(
      makeConfig({ network_announcement: "Notice" }),
    );
    fireEvent.click(screen.getByLabelText("Dismiss"));
    expect(container.querySelector("#flash-banner")).toBeNull();
    expect(sessionStorage.getItem("flash-banner-dismissed")).toBe("1");
  });

  it("does not render a previously dismissed network banner", () => {
    sessionStorage.setItem("flash-banner-dismissed", "1");
    const { container } = renderAnnouncements(
      makeConfig({ network_announcement: "Notice" }),
    );
    expect(container.querySelector("#flash-banner")).toBeNull();
  });
});

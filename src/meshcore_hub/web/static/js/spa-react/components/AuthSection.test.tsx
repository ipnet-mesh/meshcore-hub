import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthSection } from "@/components/AuthSection";
import { AppConfigProvider } from "@/context/AppConfigContext";
import { makeConfig } from "@/test/makeConfig";
import type { AppConfig } from "@/types/config";

function renderAuth(config: Partial<AppConfig> = {}) {
  return render(
    <AppConfigProvider config={makeConfig(config)}>
      <AuthSection />
    </AppConfigProvider>,
  );
}

describe("AuthSection", () => {
  it("renders nothing when OIDC is disabled", () => {
    const { container } = renderAuth({ oidc_enabled: false });
    expect(container.firstChild).toBeNull();
  });

  it("shows a login link when OIDC is enabled with no user", () => {
    renderAuth({ oidc_enabled: true });
    expect(screen.getByText("auth.login").closest("a")).toHaveAttribute(
      "href",
      "/auth/login",
    );
  });

  it("shows the avatar image when the user has a picture", () => {
    renderAuth({
      oidc_enabled: true,
      user: { sub: "u1", name: "Jane", picture: "pic.jpg" },
    });
    expect(screen.getByAltText("Jane")).toHaveAttribute("src", "pic.jpg");
  });

  it("shows initials derived from the name when no picture", () => {
    renderAuth({
      oidc_enabled: true,
      user: { sub: "u1", name: "Jane Doe" },
    });
    expect(screen.getByText("JD")).toBeInTheDocument();
  });

  it("renders role badges from config.roles", () => {
    renderAuth({
      oidc_enabled: true,
      roles: ["admin", "operator"],
      user: { sub: "u1", name: "Jane" },
    });
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(screen.getByText("operator")).toBeInTheDocument();
  });

  it("shows the user sub in debug mode", () => {
    renderAuth({
      oidc_enabled: true,
      debug: true,
      user: { sub: "user-abc", name: "Jane" },
    });
    expect(screen.getByText("user-abc")).toBeInTheDocument();
  });
});

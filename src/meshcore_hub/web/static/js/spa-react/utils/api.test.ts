import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiGet } from "./api";

function setOidcEnabled(enabled: boolean) {
  window.__APP_CONFIG__ = {
    ...(window.__APP_CONFIG__ ?? {}),
    oidc_enabled: enabled,
  } as typeof window.__APP_CONFIG__;
}

describe("apiGet auth redirect", () => {
  beforeEach(() => {
    // A real URL object's href setter rejects relative URLs, so stub a
    // minimal window.location instead.
    const locationStub = {
      href: "http://localhost/nodes?page=2",
      pathname: "/nodes",
      search: "?page=2",
      origin: "http://localhost",
    };
    vi.stubGlobal("location", locationStub);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("redirects to the login flow on 401 when OIDC is enabled", async () => {
    setOidcEnabled(true);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("unauthorized", { status: 401 }),
      ),
    );

    await expect(apiGet("/api/v1/nodes")).rejects.toThrow("API error: 401");
    expect(window.location.href).toBe(
      "/auth/login?next=%2Fnodes%3Fpage%3D2",
    );
  });

  it("does not redirect on 401 when OIDC is disabled", async () => {
    setOidcEnabled(false);
    const originalHref = window.location.href;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("unauthorized", { status: 401 }),
      ),
    );

    await expect(apiGet("/api/v1/nodes")).rejects.toThrow("API error: 401");
    expect(window.location.href).toBe(originalHref);
  });
});

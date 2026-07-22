import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";

import { CustomPagePage } from "@/pages/CustomPage";
import { AppConfigProvider } from "@/context/AppConfigContext";
import { makeConfig } from "@/test/makeConfig";
import * as api from "@/utils/api";

const originalT = window.t;

function renderPage(entry = "/pages/about") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <AppConfigProvider config={makeConfig({ network_name: "TestNet" })}>
        <Routes>
          <Route path="/pages/:slug" element={<CustomPagePage />} />
        </Routes>
      </AppConfigProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.t = (key: string) => key;
  vi.restoreAllMocks();
});

afterEach(() => {
  window.t = originalT;
});

describe("CustomPage", () => {
  it("shows a loading spinner before the fetch resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    const { container } = renderPage();
    expect(container.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders markdown content after the fetch resolves", async () => {
    vi.spyOn(api, "apiGet").mockResolvedValue({
      slug: "about",
      title: "About",
      content_markdown: "# Hello World",
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Hello World")).toBeInTheDocument();
    });
  });

  it("shows page-not-found on a 404 response", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(
      new Error("API error: 404 Not Found"),
    );
    renderPage();
    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toHaveTextContent(/page_not_found/i);
    });
  });

  it("shows a generic error on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("boom"));
    renderPage();
    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toHaveTextContent("boom");
    });
  });

  it("sets document.title from the page title and network name", async () => {
    vi.spyOn(api, "apiGet").mockResolvedValue({
      slug: "about",
      title: "About",
      content_markdown: "",
    });
    renderPage();
    await waitFor(() => {
      expect(document.title).toBe("About - TestNet");
    });
  });
});

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "@/components/ErrorBoundary";

function Thrower({ message }: { message: string }): never {
  throw new Error(message);
}

const originalT = window.t;

beforeEach(() => {
  window.t = (key: string) => key;
});

afterEach(() => {
  window.t = originalT;
});

describe("ErrorBoundary", () => {
  it("renders children when no error is thrown", () => {
    render(
      <ErrorBoundary>
        <p>all good</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("all good")).toBeInTheDocument();
  });

  it("renders the fallback UI when a child throws", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Thrower message="kaboom" />
      </ErrorBoundary>,
    );
    expect(screen.getByText("common.error")).toBeInTheDocument();
    expect(screen.getByText("common.failed_to_load_page")).toBeInTheDocument();
    expect(screen.getByText("kaboom")).toBeInTheDocument();
    const homeLink = screen.getByText("common.go_home");
    expect(homeLink.closest("a")).toHaveAttribute("href", "/");
    spy.mockRestore();
  });

  it("logs the caught error via componentDidCatch", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Thrower message="logged" />
      </ErrorBoundary>,
    );
    expect(spy).toHaveBeenCalledWith(
      "React ErrorBoundary caught:",
      expect.any(Error),
      expect.objectContaining({ componentStack: expect.any(String) }),
    );
    spy.mockRestore();
  });
});

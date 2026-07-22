import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  Loading,
  ErrorAlert,
  InfoAlert,
  SuccessAlert,
  WarningBadge,
} from "@/components/Alerts";

describe("Alerts", () => {
  it("Loading renders a centered spinner", () => {
    const { container } = render(<Loading />);
    expect(container.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("ErrorAlert renders an error-toned alert with the message", () => {
    render(<ErrorAlert message="Something broke" />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("alert-error");
    expect(alert).toHaveTextContent("Something broke");
  });

  it("InfoAlert and SuccessAlert render with the correct tones", () => {
    const { rerender } = render(<InfoAlert message="FYI" />);
    expect(screen.getByRole("alert")).toHaveClass("alert-info");
    rerender(<SuccessAlert message="Done" />);
    expect(screen.getByRole("alert")).toHaveClass("alert-success");
  });

  it("WarningBadge renders a tooltip with the message", () => {
    const { container } = render(<WarningBadge message="careful" />);
    expect(container.querySelector(".badge-warning")).not.toBeNull();
    expect(container.querySelector('[data-tip="careful"]')).not.toBeNull();
  });
});

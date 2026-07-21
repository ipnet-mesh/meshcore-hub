import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "@/components/ConfirmDialog";

function renderDialog(props: Partial<Parameters<typeof ConfirmDialog>[0]> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmDialog
      title="Delete thing"
      message="Are you sure?"
      confirmLabel="Delete"
      cancelLabel="Cancel"
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...props}
    />,
  );
  return { onConfirm, onCancel };
}

describe("ConfirmDialog", () => {
  it("renders the title and message", () => {
    renderDialog();
    expect(
      screen.getByRole("heading", { name: "Delete thing" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Are you sure?")).toBeInTheDocument();
  });

  it("calls onConfirm and onCancel from the respective buttons", () => {
    const { onConfirm, onCancel } = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("uses the error tone by default and primary when requested", () => {
    const { rerender } = render(
      <ConfirmDialog
        title="t"
        message="m"
        confirmLabel="Go"
        cancelLabel="No"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "Go" })).toHaveClass(
      "btn-error",
    );
    rerender(
      <ConfirmDialog
        title="t"
        message="m"
        confirmLabel="Go"
        cancelLabel="No"
        tone="primary"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "Go" })).toHaveClass(
      "btn-primary",
    );
  });

  it("disables both buttons and shows a spinner while saving", () => {
    const { container } = render(
      <ConfirmDialog
        title="t"
        message="m"
        confirmLabel="Delete"
        cancelLabel="Cancel"
        saving
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(container.querySelector(".loading-spinner")).not.toBeNull();
  });
});

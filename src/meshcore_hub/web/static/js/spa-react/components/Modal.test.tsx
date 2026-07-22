import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Modal } from "@/components/Modal";

describe("Modal", () => {
  it("renders the title, children and footer", () => {
    render(
      <Modal title="My Title" onClose={() => {}} footer={<span>foot</span>}>
        <p>body content</p>
      </Modal>,
    );
    expect(
      screen.getByRole("heading", { name: "My Title" }),
    ).toBeInTheDocument();
    expect(screen.getByText("body content")).toBeInTheDocument();
    expect(screen.getByText("foot")).toBeInTheDocument();
  });

  it("omits the footer action row when no footer is given", () => {
    const { container } = render(
      <Modal title="t" onClose={() => {}}>
        <p>body</p>
      </Modal>,
    );
    expect(container.querySelector(".modal-action")).toBeNull();
  });

  it("applies the large size class", () => {
    const { container } = render(
      <Modal title="t" size="lg" onClose={() => {}}>
        <p>body</p>
      </Modal>,
    );
    expect(container.querySelector(".modal-box-lg")).not.toBeNull();
  });

  it("calls onClose when the backdrop button is clicked", () => {
    const onClose = vi.fn();
    render(
      <Modal title="t" onClose={onClose}>
        <p>body</p>
      </Modal>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});

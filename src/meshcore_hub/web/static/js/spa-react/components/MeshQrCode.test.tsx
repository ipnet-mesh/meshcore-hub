import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MeshQrCode } from "@/components/MeshQrCode";

describe("MeshQrCode", () => {
  it("renders an svg QR code inside the white padded wrapper by default", () => {
    const { container } = render(<MeshQrCode value="meshcore://test" />);
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.firstChild).toHaveClass("bg-white");
    expect(container.firstChild).toHaveClass("rounded-box");
  });

  it("accepts a custom className override", () => {
    const { container } = render(
      <MeshQrCode value="x" className="bg-white p-2 rounded-box shadow-lg" />,
    );
    expect(container.firstChild).toHaveClass("shadow-lg");
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  Field,
  RedactedNotice,
  channelNameDisplay,
} from "@/components/PacketParts";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en" },
  }),
}));

describe("Field", () => {
  it("renders a label and its value", () => {
    render(<Field label="Time">12:00</Field>);
    expect(screen.getByText("Time")).toBeInTheDocument();
    expect(screen.getByText("12:00")).toBeInTheDocument();
  });
});

describe("channelNameDisplay", () => {
  it("renders an em dash for a null channel index", () => {
    render(<>{channelNameDisplay(new Map(), null)}</>);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders 'name (idx)' for a known channel", () => {
    render(<>{channelNameDisplay(new Map([[3, "General"]]), 3)}</>);
    expect(screen.getByText("General (3)")).toBeInTheDocument();
  });

  it("renders just the index for an unknown channel", () => {
    render(<>{channelNameDisplay(new Map(), 7)}</>);
    expect(screen.getByText("7")).toBeInTheDocument();
  });
});

describe("RedactedNotice", () => {
  it("renders a warning notice", () => {
    const { container } = render(<RedactedNotice />);
    expect(container.querySelector(".alert-warning")).not.toBeNull();
    expect(container.textContent).toContain("packets.redacted_notice");
  });
});

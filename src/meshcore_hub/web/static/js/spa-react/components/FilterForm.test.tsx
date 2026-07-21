import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { describe, expect, it, vi } from "vitest";

import {
  FilterField,
  FilterForm,
  OperatorSelect,
  submitOnEnter,
} from "@/components/FilterForm";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en" },
  }),
}));

const profiles = [
  { id: "1", name: "Alice", callsign: "AL", user_id: "u1" },
  { id: "2", name: "Bob", callsign: null, user_id: "u2" },
];

describe("OperatorSelect", () => {
  it("renders an all-operators option plus formatted profile options", () => {
    render(<OperatorSelect profiles={profiles} defaultValue="" />);
    expect(screen.getByText("common.all_operators")).toBeInTheDocument();
    expect(screen.getByText("Alice (AL)")).toBeInTheDocument();
    // No callsign -> falls back to the plain name
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });

  it("supports controlled value and onChange", () => {
    const onChange = vi.fn();
    render(
      <OperatorSelect profiles={profiles} value="1" onChange={onChange} />,
    );
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select.value).toBe("1");
    fireEvent.change(select, { target: { value: "2" } });
    expect(onChange).toHaveBeenCalledOnce();
  });
});

describe("FilterField", () => {
  it("renders a label wrapping the control", () => {
    render(
      <FilterField label="Search">
        <input data-testid="control" />
      </FilterField>,
    );
    expect(screen.getByText("Search")).toBeInTheDocument();
    expect(screen.getByTestId("control")).toBeInTheDocument();
  });
});

describe("submitOnEnter", () => {
  it("submits the form on Enter", () => {
    const requestSubmit = vi
      .spyOn(HTMLFormElement.prototype, "requestSubmit")
      .mockImplementation(() => {});
    render(
      <form>
        <input data-testid="inp" onKeyDown={submitOnEnter} />
      </form>,
    );
    fireEvent.keyDown(screen.getByTestId("inp"), { key: "Enter" });
    expect(requestSubmit).toHaveBeenCalledOnce();
    requestSubmit.mockRestore();
  });

  it("does nothing for other keys", () => {
    const requestSubmit = vi
      .spyOn(HTMLFormElement.prototype, "requestSubmit")
      .mockImplementation(() => {});
    render(
      <form>
        <input data-testid="inp" onKeyDown={submitOnEnter} />
      </form>,
    );
    fireEvent.keyDown(screen.getByTestId("inp"), { key: "a" });
    expect(requestSubmit).not.toHaveBeenCalled();
    requestSubmit.mockRestore();
  });
});

describe("FilterForm clear navigation", () => {
  function LocationProbe() {
    const location = useLocation();
    return (
      <div data-testid="loc">{location.pathname + location.search}</div>
    );
  }

  it("clears filters via client-side navigation (no full reload)", () => {
    render(
      <MemoryRouter initialEntries={["/nodes?search=foo"]}>
        <FilterForm basePath="/nodes">
          <input name="search" defaultValue="foo" />
        </FilterForm>
        <LocationProbe />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("loc").textContent).toBe("/nodes?search=foo");
    fireEvent.click(screen.getByText("common.clear"));
    expect(screen.getByTestId("loc").textContent).toBe("/nodes");
  });
});

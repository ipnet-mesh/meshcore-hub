import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-chartjs-2", () => ({
  Line: () => <div data-testid="mock-line-chart" />,
  Bar: () => <div data-testid="mock-bar-chart" />,
}));

vi.mock("@/utils/charts", () => ({
  buildActivityChart: (a: unknown, m: unknown) =>
    a != null || m != null ? { data: {}, options: {} } : null,
  buildLineChart: (d: unknown) => (d != null ? { data: {}, options: {} } : null),
  buildStackedBar: (b: unknown) => (b != null ? { data: {}, options: {} } : null),
  buildRoutesTrend: (r: unknown) => (r != null ? { data: {}, options: {} } : null),
  buildRouteDetailStrip: (d: unknown) =>
    d != null ? { data: {}, options: {} } : null,
}));

import {
  ActivityChart,
  TrendLineChart,
  StackedBarChart,
  RoutesTrendChart,
  RouteDetailStrip,
} from "@/components/charts/Charts";

// Since @/utils/charts is mocked, the actual data shape is irrelevant —
// these casts just satisfy the component prop types at compile time.
const DATA = { data: [] } as never;

describe("Chart wrappers", () => {
  it("ActivityChart renders a Line when data is present", () => {
    render(<ActivityChart advertData={DATA} messageData={null} />);
    expect(screen.getByTestId("mock-line-chart")).toBeInTheDocument();
  });

  it("ActivityChart renders nothing when both series are null", () => {
    const { container } = render(
      <ActivityChart advertData={null} messageData={null} />,
    );
    expect(container.querySelector('[data-testid="mock-line-chart"]')).toBeNull();
  });

  it("TrendLineChart renders a Line when data is provided", () => {
    render(
      <TrendLineChart
        data={DATA}
        label="x"
        borderColor="#f00"
        backgroundColor="#0f0"
      />,
    );
    expect(screen.getByTestId("mock-line-chart")).toBeInTheDocument();
  });

  it("StackedBarChart renders a Bar when buckets are provided", () => {
    render(<StackedBarChart buckets={DATA} colors={["#f00"]} />);
    expect(screen.getByTestId("mock-bar-chart")).toBeInTheDocument();
  });

  it("RoutesTrendChart renders a Line when routes are provided", () => {
    render(<RoutesTrendChart routes={DATA} />);
    expect(screen.getByTestId("mock-line-chart")).toBeInTheDocument();
  });

  it("RouteDetailStrip renders a Bar when data is provided", () => {
    render(<RouteDetailStrip data={DATA} />);
    expect(screen.getByTestId("mock-bar-chart")).toBeInTheDocument();
  });
});

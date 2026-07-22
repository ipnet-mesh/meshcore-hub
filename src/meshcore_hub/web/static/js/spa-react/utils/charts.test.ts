import { describe, expect, it } from "vitest";
import type { TFunction } from "i18next";

import {
  averageRouteTier,
  buildActivityChart,
  buildLineChart,
  buildRouteDetailStrip,
  buildRoutesTrend,
  buildStackedBar,
  ChartColors,
  routeQualityToTier,
  type ActivitySeries,
  type BreakdownBucket,
  type RouteOverviewEntry,
} from "@/utils/charts";

const t = ((key: string) => key) as unknown as TFunction;

const dayLabel = (date: string) =>
  new Date(date).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
  });

const series = (counts: number[]): ActivitySeries => ({
  data: counts.map((count, i) => ({
    date: `2026-02-0${i + 1}`,
    count,
  })),
});

describe("routeQualityToTier", () => {
  it("maps clear/marginal through and everything else to failing", () => {
    expect(routeQualityToTier("clear")).toBe("clear");
    expect(routeQualityToTier("marginal")).toBe("marginal");
    expect(routeQualityToTier("failing")).toBe("failing");
    expect(routeQualityToTier("unknown")).toBe("failing");
    expect(routeQualityToTier("no_coverage")).toBe("failing");
    expect(routeQualityToTier(null)).toBe("failing");
    expect(routeQualityToTier(undefined)).toBe("failing");
  });
});

describe("averageRouteTier", () => {
  it("falls back to failing on empty/absent history", () => {
    expect(averageRouteTier(null)).toBe("failing");
    expect(averageRouteTier([])).toBe("failing");
  });

  it("buckets the mean tier (clear=2, marginal=1, failing=0)", () => {
    const q = (quality: string) => [{ quality }];
    expect(averageRouteTier(q("clear"))).toBe("clear");
    expect(averageRouteTier(q("marginal"))).toBe("marginal");
    expect(averageRouteTier(q("failing"))).toBe("failing");

    // mean (2+1)/2 = 1.5 -> clear
    expect(averageRouteTier([{ quality: "clear" }, { quality: "marginal" }])).toBe(
      "clear",
    );
    // mean (2+0)/2 = 1.0 -> marginal (>= 0.75)
    expect(averageRouteTier([{ quality: "clear" }, { quality: "failing" }])).toBe(
      "marginal",
    );
    // mean (1+0)/2 = 0.5 -> failing
    expect(
      averageRouteTier([{ quality: "marginal" }, { quality: "failing" }]),
    ).toBe("failing");
  });
});

describe("buildLineChart", () => {
  it("returns null for missing/empty data", () => {
    expect(buildLineChart(null, "L", "b", "bg", true)).toBeNull();
    expect(buildLineChart({ data: [] }, "L", "b", "bg", true)).toBeNull();
  });

  it("builds a single filled dataset with formatted labels", () => {
    const cfg = buildLineChart(
      series([5, 10]),
      "Nodes",
      "border",
      "fill",
      true,
    );
    expect(cfg).not.toBeNull();
    expect(cfg!.data.labels).toEqual([dayLabel("2026-02-01"), dayLabel("2026-02-02")]);
    expect(cfg!.data.datasets).toHaveLength(1);
    const ds = cfg!.data.datasets[0] as { data: number[]; label: string; fill: boolean };
    expect(ds.label).toBe("Nodes");
    expect(ds.data).toEqual([5, 10]);
    expect(ds.fill).toBe(true);
  });
});

describe("buildActivityChart", () => {
  it("returns null when both series are absent", () => {
    expect(buildActivityChart(null, null, t)).toBeNull();
  });

  it("builds one dataset when only adverts are provided", () => {
    const cfg = buildActivityChart(series([3, 4]), null, t);
    expect(cfg).not.toBeNull();
    expect(cfg!.data.datasets).toHaveLength(1);
    expect((cfg!.data.datasets[0] as { label: string }).label).toBe(
      "entities.advertisements",
    );
  });

  it("builds two datasets when both series are provided", () => {
    const cfg = buildActivityChart(series([3, 4]), series([1, 2]), t);
    expect(cfg).not.toBeNull();
    expect(cfg!.data.datasets).toHaveLength(2);
    const labels = cfg!.data.datasets.map((d) => (d as { label: string }).label);
    expect(labels).toEqual(["entities.advertisements", "entities.messages"]);
  });
});

describe("buildStackedBar", () => {
  it("returns null for empty buckets or zero total", () => {
    expect(buildStackedBar(null, ["red"])).toBeNull();
    expect(buildStackedBar([], ["red"])).toBeNull();
    const zero: BreakdownBucket[] = [
      { label: "a", count: 0 },
      { label: "b", count: 0 },
    ];
    expect(buildStackedBar(zero, ["red"])).toBeNull();
  });

  it("produces percentage datasets that sum to 100 with rawCount preserved", () => {
    const buckets: BreakdownBucket[] = [
      { label: "a", count: 30 },
      { label: "b", count: 70 },
    ];
    const cfg = buildStackedBar(buckets, ["red", "blue"]);
    expect(cfg).not.toBeNull();
    const datasets = cfg!.data.datasets as {
      data: number[];
      rawCount: number;
      backgroundColor: string;
    }[];
    expect(datasets).toHaveLength(2);
    expect(datasets[0].data[0] + datasets[1].data[0]).toBeCloseTo(100);
    expect(datasets[0].rawCount).toBe(30);
    expect(datasets[1].rawCount).toBe(70);
    expect(datasets[0].backgroundColor).toBe("red");
    expect(datasets[1].backgroundColor).toBe("blue");
  });
});

describe("buildRoutesTrend", () => {
  it("returns null for empty routes or routes without history", () => {
    expect(buildRoutesTrend(null, t)).toBeNull();
    expect(buildRoutesTrend([], t)).toBeNull();
    expect(
      buildRoutesTrend([{ from_label: "A", to_label: "B", history: [] }], t),
    ).toBeNull();
  });

  it("sorts by matched_count, uses categorical tiers, and colors by average tier", () => {
    const routes: RouteOverviewEntry[] = [
      {
        from_label: "A",
        to_label: "B",
        matched_count: 1,
        history: [
          { date: "2026-02-01", quality: "clear", matched_count: 1 },
          { date: "2026-02-02", quality: "clear", matched_count: 1 },
        ],
      },
      {
        from_label: "C",
        to_label: "D",
        matched_count: 9,
        history: [
          { date: "2026-02-01", quality: "failing", matched_count: 9 },
          { date: "2026-02-02", quality: "failing", matched_count: 9 },
        ],
      },
    ];
    const cfg = buildRoutesTrend(routes, t);
    expect(cfg).not.toBeNull();
    const datasets = cfg!.data.datasets as unknown as {
      label: string;
      data: string[];
      borderColor: string;
      _matched: number[];
    }[];
    // Higher matched_count first
    expect(datasets[0].label).toBe("C \u2192 D");
    expect(datasets[0].data).toEqual(["failing", "failing"]);
    expect(datasets[0].borderColor).toBe(ChartColors.quality.failing);
    expect(datasets[0]._matched).toEqual([9, 9]);
    expect(datasets[1].data).toEqual(["clear", "clear"]);
    expect(datasets[1].borderColor).toBe(ChartColors.quality.clear);
    expect(cfg!.data.labels).toEqual([
      dayLabel("2026-02-01"),
      dayLabel("2026-02-02"),
    ]);
  });

  it("respects maxRoutes", () => {
    const routes: RouteOverviewEntry[] = Array.from({ length: 8 }, (_, i) => ({
      from_label: `A${i}`,
      to_label: "B",
      matched_count: i,
      history: [{ date: "2026-02-01", quality: "clear", matched_count: i }],
    }));
    const cfg = buildRoutesTrend(routes, t, 6);
    expect(cfg!.data.datasets).toHaveLength(6);
  });
});

describe("buildRouteDetailStrip", () => {
  it("returns null for missing/empty history", () => {
    expect(buildRouteDetailStrip(null, t)).toBeNull();
    expect(buildRouteDetailStrip({ data: [] }, t)).toBeNull();
    expect(buildRouteDetailStrip({}, t)).toBeNull();
  });

  it("produces one colored segment per day", () => {
    const cfg = buildRouteDetailStrip(
      {
        data: [
          { date: "2026-02-01", quality: "clear", matched_count: 5 },
          { date: "2026-02-02", quality: "failing", matched_count: 2 },
        ],
      },
      t,
    );
    expect(cfg).not.toBeNull();
    const datasets = cfg!.data.datasets as {
      data: number[];
      backgroundColor: string;
      _quality: string;
      _matched_count: number;
    }[];
    expect(datasets).toHaveLength(2);
    expect(datasets[0].data).toEqual([1]);
    expect(datasets[0].backgroundColor).toBe(ChartColors.quality.clear);
    expect(datasets[0]._quality).toBe("clear");
    expect(datasets[0]._matched_count).toBe(5);
    expect(datasets[1].backgroundColor).toBe(ChartColors.quality.failing);
    expect(datasets[1]._matched_count).toBe(2);
  });

  it("falls back to no_coverage color for unknown quality", () => {
    const cfg = buildRouteDetailStrip(
      { data: [{ date: "2026-02-01", quality: "weird", matched_count: 0 }] },
      t,
    );
    const ds = cfg!.data.datasets[0] as { backgroundColor: string };
    expect(ds.backgroundColor).toBe(ChartColors.quality.no_coverage);
  });
});

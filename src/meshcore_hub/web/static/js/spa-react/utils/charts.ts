import Chart from "chart.js/auto";
import type {
  ChartData,
  ChartDataset,
  ChartOptions,
  TooltipItem,
} from "chart.js";
import type { TFunction } from "i18next";

Chart.defaults.font.family =
  '"IBM Plex Sans", ui-sans-serif, system-ui, sans-serif';

export interface ActivityPoint {
  date: string;
  count: number;
}

export interface ActivitySeries {
  data: ActivityPoint[];
}

export interface BreakdownBucket {
  label: string;
  count: number;
}

export interface RouteHistoryDay {
  date: string;
  quality?: string | null;
  matched_count?: number | null;
}

export interface RouteHistory {
  data?: RouteHistoryDay[];
}

export interface RouteOverviewEntry {
  from_label: string;
  to_label: string;
  matched_count?: number | null;
  history?: RouteHistoryDay[];
}

export interface ChartConfig<T extends "line" | "bar"> {
  data: ChartData<T>;
  options: ChartOptions<T>;
}

function formatNumber(v: number): string {
  return new Intl.NumberFormat().format(v);
}

function getCSSColor(varName: string, fallback: string): string {
  return (
    getComputedStyle(document.documentElement)
      .getPropertyValue(varName)
      .trim() || fallback
  );
}

function withAlpha(color: string, alpha: number): string {
  return color.replace(")", " / " + alpha + ")");
}

export const ChartColors = {
  get nodes() {
    return getCSSColor("--color-nodes", "oklch(0.65 0.24 265)");
  },
  get nodesFill() {
    return withAlpha(this.nodes, 0.1);
  },
  get adverts() {
    return getCSSColor("--color-adverts", "oklch(0.7 0.17 330)");
  },
  get advertsFill() {
    return withAlpha(this.adverts, 0.1);
  },
  get messages() {
    return getCSSColor("--color-messages", "oklch(0.75 0.18 180)");
  },
  get messagesFill() {
    return withAlpha(this.messages, 0.1);
  },
  get packets() {
    return getCSSColor("--color-packets", "oklch(0.72 0.17 145)");
  },
  get packetsFill() {
    return withAlpha(this.packets, 0.1);
  },
  get routes() {
    return getCSSColor("--color-routes", "oklch(0.72 0.17 30)");
  },
  get routesFill() {
    return withAlpha(this.routes, 0.1);
  },

  grid: "oklch(0.4 0 0 / 0.2)",
  text: "oklch(0.7 0 0)",
  tooltipBg: "oklch(0.25 0 0)",
  tooltipText: "oklch(0.9 0 0)",
  tooltipBorder: "oklch(0.4 0 0)",

  breakdown: [
    "oklch(0.65 0.24 265)",
    "oklch(0.7 0.17 330)",
    "oklch(0.75 0.18 180)",
    "oklch(0.72 0.17 145)",
    "oklch(0.7 0.19 80)",
    "oklch(0.65 0.22 25)",
    "oklch(0.55 0 0)",
  ],

  quality: {
    clear: "oklch(0.72 0.17 145)",
    marginal: "oklch(0.75 0.18 85)",
    failing: "oklch(0.62 0.24 25)",
    no_coverage: "oklch(0.65 0.15 250)",
    disabled: "oklch(0.55 0 0)",
  } as Record<string, string>,
};

function createChartOptions(showLegend: boolean): ChartOptions<"line"> {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: showLegend,
        position: "top",
        align: "end",
        labels: {
          color: ChartColors.text,
          boxWidth: 12,
          padding: 8,
        },
      },
      tooltip: {
        mode: "index",
        intersect: false,
        backgroundColor: ChartColors.tooltipBg,
        titleColor: ChartColors.tooltipText,
        bodyColor: ChartColors.tooltipText,
        borderColor: ChartColors.tooltipBorder,
        borderWidth: 1,
        callbacks: {
          label: (ctx: TooltipItem<"line">) => {
            const label = ctx.dataset.label || "";
            const value = formatNumber(ctx.parsed.y ?? 0);
            return label ? label + ": " + value : value;
          },
        },
      },
    },
    scales: {
      x: {
        grid: { color: ChartColors.grid },
        ticks: {
          color: ChartColors.text,
          maxRotation: 45,
          minRotation: 45,
          maxTicksLimit: 10,
        },
      },
      y: {
        beginAtZero: true,
        grid: { color: ChartColors.grid },
        ticks: {
          color: ChartColors.text,
          precision: 0,
          callback: (value) => formatNumber(Number(value)),
        },
      },
    },
    interaction: {
      mode: "nearest",
      axis: "x",
      intersect: false,
    },
  };
}

function formatDateLabels(data: { date: string }[]): string[] {
  return data.map((d) => {
    const date = new Date(d.date);
    return date.toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
    });
  });
}

export function routeQualityToTier(q: string | null | undefined): string {
  if (q === "clear") return "clear";
  if (q === "marginal") return "marginal";
  return "failing";
}

export function averageRouteTier(
  history: { quality?: string | null }[] | null | undefined,
): string {
  if (!history || history.length === 0) return "failing";
  let sum = 0;
  for (const entry of history) {
    const tier = routeQualityToTier(entry.quality);
    sum += tier === "clear" ? 2 : tier === "marginal" ? 1 : 0;
  }
  const mean = sum / history.length;
  if (mean >= 1.5) return "clear";
  if (mean >= 0.75) return "marginal";
  return "failing";
}

export function buildLineChart(
  data: ActivitySeries | null | undefined,
  label: string,
  borderColor: string,
  backgroundColor: string,
  fill: boolean,
): ChartConfig<"line"> | null {
  if (!data || !data.data || data.data.length === 0) return null;
  return {
    data: {
      labels: formatDateLabels(data.data),
      datasets: [
        {
          label,
          data: data.data.map((d) => d.count),
          borderColor,
          backgroundColor,
          fill,
          tension: 0.3,
          pointRadius: 2,
          pointHoverRadius: 5,
        },
      ],
    },
    options: createChartOptions(false),
  };
}

export function buildActivityChart(
  advertData: ActivitySeries | null | undefined,
  messageData: ActivitySeries | null | undefined,
  t: TFunction,
): ChartConfig<"line"> | null {
  const datasets: ChartDataset<"line">[] = [];
  let labels: string[] | null = null;

  if (advertData && advertData.data && advertData.data.length > 0) {
    if (!labels) labels = formatDateLabels(advertData.data);
    datasets.push({
      label: t("entities.advertisements"),
      data: advertData.data.map((d) => d.count),
      borderColor: ChartColors.adverts,
      backgroundColor: ChartColors.advertsFill,
      fill: true,
      tension: 0.3,
      pointRadius: 2,
      pointHoverRadius: 5,
    });
  }

  if (messageData && messageData.data && messageData.data.length > 0) {
    if (!labels) labels = formatDateLabels(messageData.data);
    datasets.push({
      label: t("entities.messages"),
      data: messageData.data.map((d) => d.count),
      borderColor: ChartColors.messages,
      backgroundColor: ChartColors.messagesFill,
      fill: true,
      tension: 0.3,
      pointRadius: 2,
      pointHoverRadius: 5,
    });
  }

  if (datasets.length === 0 || !labels) return null;
  return { data: { labels, datasets }, options: createChartOptions(true) };
}

type StackedBarDataset = ChartDataset<"bar"> & { rawCount?: number };

export function buildStackedBar(
  buckets: BreakdownBucket[] | null | undefined,
  colors: string[],
): ChartConfig<"bar"> | null {
  if (!buckets || buckets.length === 0) return null;
  const total = buckets.reduce((sum, b) => sum + b.count, 0);
  if (total === 0) return null;

  const datasets: StackedBarDataset[] = buckets.map((bucket, i) => {
    const pct = (bucket.count / total) * 100;
    return {
      label: bucket.label,
      data: [pct],
      backgroundColor: colors[i % colors.length],
      borderColor: colors[i % colors.length],
      borderWidth: 1,
      rawCount: bucket.count,
    };
  });

  return {
    data: { labels: [""], datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: ChartColors.tooltipBg,
          titleColor: ChartColors.tooltipText,
          bodyColor: ChartColors.tooltipText,
          borderColor: ChartColors.tooltipBorder,
          borderWidth: 1,
          callbacks: {
            label: (ctx: TooltipItem<"bar">) => {
              const ds = ctx.dataset as StackedBarDataset;
              const label = ds.label || "";
              const count = formatNumber(ds.rawCount ?? 0);
              const pct = (ctx.parsed.x ?? 0).toFixed(1);
              return label + ": " + count + " (" + pct + "%)";
            },
          },
        },
      },
      scales: {
        x: {
          max: 100,
          stacked: true,
          grid: { color: ChartColors.grid },
          ticks: {
            color: ChartColors.text,
            callback: (value) => value + "%",
          },
        },
        y: {
          stacked: true,
          grid: { display: false },
          ticks: { display: false },
        },
      },
      interaction: {
        mode: "nearest",
        intersect: false,
      },
    },
  };
}

type RouteTrendDataset = ChartDataset<"line"> & { _matched?: number[] };

export function buildRoutesTrend(
  routes: RouteOverviewEntry[] | null | undefined,
  t: TFunction,
  maxRoutes = 6,
): ChartConfig<"line"> | null {
  if (!routes || routes.length === 0) return null;

  const tierOrder = ["failing", "marginal", "clear"];
  const tierColor = (tier: string): string =>
    ChartColors.quality[tier] || ChartColors.quality.failing;

  const sorted = routes
    .slice()
    .sort((a, b) => (b.matched_count || 0) - (a.matched_count || 0));
  const top = sorted.slice(0, maxRoutes);

  let labels: string[] = [];
  for (const entry of top) {
    if (entry.history && entry.history.length > labels.length) {
      labels = formatDateLabels(entry.history);
    }
  }
  if (labels.length === 0) return null;

  const datasets: RouteTrendDataset[] = top.map((entry) => {
    const history = entry.history || [];
    const avgTier = averageRouteTier(history);
    return {
      label: entry.from_label + " \u2192 " + entry.to_label,
      data: history.map((d) => routeQualityToTier(d.quality)),
      borderColor: tierColor(avgTier),
      backgroundColor: "transparent",
      fill: false,
      tension: 0.3,
      cubicInterpolationMode: "monotone",
      pointRadius: 2,
      pointHoverRadius: 5,
      spanGaps: true,
      _matched: history.map((d) => d.matched_count || 0),
    } as unknown as RouteTrendDataset;
  });

  const opts = createChartOptions(false);
  opts.scales = {
    ...opts.scales,
    y: {
      type: "category",
      labels: tierOrder,
      reverse: true,
      grid: { color: ChartColors.grid },
      ticks: {
        color: ChartColors.text,
        callback: (_value, index) => {
          const tier = tierOrder[index];
          return t("routes.quality_" + tier);
        },
      },
    },
  };
  opts.plugins = {
    ...opts.plugins,
    tooltip: {
      ...opts.plugins?.tooltip,
      callbacks: {
        title: (items: TooltipItem<"line">[]) => items[0].label,
        label: (ctx: TooltipItem<"line">) => {
          const ds = ctx.dataset as RouteTrendDataset;
          const tier = tierOrder[ctx.parsed.y as number] || "failing";
          const tierLabel = t("routes.quality_" + tier);
          const matched = ds._matched?.[ctx.dataIndex] ?? 0;
          return (ds.label || "") + ": " + tierLabel + " (" + matched + ")";
        },
      },
    },
  };

  return {
    data: { labels, datasets },
    options: opts as ChartOptions<"line">,
  };
}

type StripDataset = ChartDataset<"bar"> & {
  _quality?: string;
  _matched_count?: number;
};

export function buildRouteDetailStrip(
  routeData: RouteHistory | null | undefined,
  t: TFunction,
): ChartConfig<"bar"> | null {
  if (!routeData || !routeData.data || routeData.data.length === 0) return null;

  const datasets: StripDataset[] = routeData.data.map((day) => {
    const color =
      ChartColors.quality[day.quality ?? ""] || ChartColors.quality.no_coverage;
    return {
      label: day.date,
      data: [1],
      backgroundColor: color,
      borderColor: color,
      borderWidth: 1,
      _quality: day.quality ?? "unknown",
      _matched_count: day.matched_count || 0,
    };
  });

  return {
    data: { labels: [""], datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: ChartColors.tooltipBg,
          titleColor: ChartColors.tooltipText,
          bodyColor: ChartColors.tooltipText,
          borderColor: ChartColors.tooltipBorder,
          borderWidth: 1,
          callbacks: {
            title: (ctx: TooltipItem<"bar">[]) => ctx[0].dataset.label || "",
            label: (ctx: TooltipItem<"bar">) => {
              const ds = ctx.dataset as StripDataset;
              const q = ds._quality || "unknown";
              const label = t("routes.quality_" + q);
              return label + " (" + (ds._matched_count ?? 0) + ")";
            },
          },
        },
      },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { display: false } },
        y: { stacked: true, grid: { display: false }, ticks: { display: false } },
      },
      interaction: { mode: "nearest", intersect: true },
    },
  };
}

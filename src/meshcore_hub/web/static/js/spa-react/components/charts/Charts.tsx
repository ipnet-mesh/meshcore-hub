import type { ReactNode } from "react";
import { Bar, Line } from "react-chartjs-2";
import { useTranslation } from "react-i18next";

import {
  buildActivityChart,
  buildLineChart,
  buildRouteDetailStrip,
  buildRoutesTrend,
  buildStackedBar,
  type ActivitySeries,
  type BreakdownBucket,
  type RouteHistory,
  type RouteOverviewEntry,
} from "@/utils/charts";

function ChartFrame({
  className,
  children,
}: {
  className: string;
  children: ReactNode;
}) {
  return <div className={className}>{children}</div>;
}

export function ActivityChart({
  advertData,
  messageData,
}: {
  advertData: ActivitySeries | null;
  messageData: ActivitySeries | null;
}) {
  const { t } = useTranslation();
  const cfg = buildActivityChart(advertData, messageData, t);
  return (
    <ChartFrame className="h-48">
      {cfg && <Line data={cfg.data} options={cfg.options} />}
    </ChartFrame>
  );
}

export function TrendLineChart({
  data,
  label,
  borderColor,
  backgroundColor,
  fill = true,
}: {
  data: ActivitySeries | null;
  label: string;
  borderColor: string;
  backgroundColor: string;
  fill?: boolean;
}) {
  const cfg = buildLineChart(data, label, borderColor, backgroundColor, fill);
  return (
    <ChartFrame className="h-32">
      {cfg && <Line data={cfg.data} options={cfg.options} />}
    </ChartFrame>
  );
}

export function StackedBarChart({
  buckets,
  colors,
}: {
  buckets: BreakdownBucket[] | null;
  colors: string[];
}) {
  const cfg = buildStackedBar(buckets, colors);
  return (
    <ChartFrame className="h-32">
      {cfg && <Bar data={cfg.data} options={cfg.options} />}
    </ChartFrame>
  );
}

export function RoutesTrendChart({
  routes,
}: {
  routes: RouteOverviewEntry[] | null;
}) {
  const { t } = useTranslation();
  const cfg = buildRoutesTrend(routes, t);
  return (
    <ChartFrame className="h-32">
      {cfg && <Line data={cfg.data} options={cfg.options} />}
    </ChartFrame>
  );
}

export function RouteDetailStrip({ data }: { data: RouteHistory | undefined }) {
  const { t } = useTranslation();
  const cfg = buildRouteDetailStrip(data, t);
  return (
    <div style={{ height: "40px" }}>
      {cfg && <Bar data={cfg.data} options={cfg.options} />}
    </div>
  );
}

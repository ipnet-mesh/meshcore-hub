export type TranslateFn = (
  key: string,
  params?: Record<string, unknown>,
) => string;

export interface RouteResultLike {
  quality?: string | null;
  state?: string | null;
}

export interface RouteItemLike {
  quality_avg?: string | null;
  enabled?: boolean;
  route_result?: RouteResultLike | null;
}

export function qualityOf(route: RouteItemLike): string {
  return route.quality_avg || route.route_result?.quality || "unknown";
}

export function qualityBadgeClass(quality: string, enabled: boolean): string {
  if (!enabled) return "badge-neutral";
  const map: Record<string, string> = {
    clear: "badge-success",
    marginal: "badge-warning",
    failing: "badge-error",
    no_coverage: "badge-info",
    unknown: "badge-ghost",
  };
  return map[quality] || "badge-ghost";
}

export function qualityLabel(
  quality: string,
  enabled: boolean,
  t: TranslateFn,
): string {
  if (!enabled) return t("routes.disabled");
  const map: Record<string, string> = {
    clear: t("routes.quality_clear"),
    marginal: t("routes.quality_marginal"),
    failing: t("routes.quality_failing"),
    no_coverage: t("routes.quality_no_coverage"),
    unknown: t("routes.quality_unknown"),
  };
  return map[quality] || quality || t("routes.quality_unknown");
}

export function diagnosisText(route: RouteItemLike, t: TranslateFn): string {
  const result = route.route_result;
  if (!result || !route.enabled) return "";
  if (result.state === "healthy") return t("routes.diagnosis_healthy");
  if (result.state === "unhealthy") return t("routes.diagnosis_unhealthy");
  if (result.state === "no_coverage") return t("routes.diagnosis_no_coverage");
  return "";
}

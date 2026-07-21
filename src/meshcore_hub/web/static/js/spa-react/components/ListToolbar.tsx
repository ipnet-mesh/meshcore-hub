import { useTranslation } from "react-i18next";

import { WarningBadge } from "@/components/Alerts";
import { AutoRefreshToggle } from "@/components/AutoRefreshToggle";
import { CountBadge } from "@/components/Badges";
import { FilterToggle } from "@/components/FilterForm";
import { formatNumber } from "@/utils/format";

export interface ListToolbarAutoRefresh {
  paused: boolean;
  onToggle: () => void;
  intervalSeconds: number;
}

export function ListToolbar({
  total,
  error,
  autoRefresh,
  filterToggle,
}: {
  total: number | null;
  error?: string | null;
  autoRefresh: ListToolbarAutoRefresh;
  filterToggle?: { open: boolean; onChange: () => void };
}) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 mb-4">
      {total !== null && (
        <CountBadge>{t("common.total", { count: formatNumber(total) })}</CountBadge>
      )}
      {error && <WarningBadge message={error} />}
      <div className="ml-auto flex items-center gap-3">
        <AutoRefreshToggle
          paused={autoRefresh.paused}
          onToggle={autoRefresh.onToggle}
          intervalSeconds={autoRefresh.intervalSeconds}
        />
        {filterToggle && <FilterToggle {...filterToggle} />}
      </div>
    </div>
  );
}

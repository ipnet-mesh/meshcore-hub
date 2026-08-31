import { useTranslation } from "react-i18next";

import { WarningBadge } from "@/components/Alerts";
import { AutoRefreshToggle } from "@/components/AutoRefreshToggle";
import { CountBadge } from "@/components/Badges";
import { FilterToggle } from "@/components/FilterForm";
import { IconRss } from "@/components/icons";
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
  feedHref,
}: {
  total: number | null;
  error?: string | null;
  autoRefresh: ListToolbarAutoRefresh;
  filterToggle?: { open: boolean; onChange: () => void };
  feedHref?: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 mb-4">
      {total !== null && (
        <CountBadge>{t("common.total", { count: formatNumber(total) })}</CountBadge>
      )}
      {error && <WarningBadge message={error} />}
      <div className="ml-auto flex items-center gap-3">
        {feedHref && (
          <a
            href={feedHref}
            title="RSS"
            aria-label="RSS"
            data-testid="feed-link"
            className="opacity-70 hover:opacity-100 transition-opacity"
          >
            <IconRss className="h-4 w-4" />
          </a>
        )}
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

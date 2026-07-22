import { useTranslation } from "react-i18next";
import { Link } from "react-router";

function buildSortUrl(
  basePath: string,
  params: Record<string, string | string[]>,
  nextSort: string,
  nextOrder: string,
): string {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      if (Array.isArray(value)) {
        value.forEach((item) => sp.append(key, String(item)));
      } else {
        sp.set(key, String(value));
      }
    }
  }
  if (nextSort && nextOrder) {
    sp.set("sort", nextSort);
    sp.set("order", nextOrder);
  }
  const qs = sp.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

interface SortableTableHeaderProps {
  label: string;
  sortKey: string;
  currentSort: string;
  currentOrder: string;
  basePath: string;
  params?: Record<string, string | string[]>;
}

export function SortableTableHeader({
  label,
  sortKey,
  currentSort,
  currentOrder,
  basePath,
  params = {},
}: SortableTableHeaderProps) {
  let indicator = "";
  let nextOrder: string;

  if (currentSort !== sortKey) {
    nextOrder = "asc";
  } else if (currentOrder === "asc") {
    nextOrder = "desc";
    indicator = " \u25B4";
  } else {
    nextOrder = "asc";
    indicator = " \u25BE";
  }

  const url = buildSortUrl(basePath, params, sortKey, nextOrder);

  return (
    <th>
      <Link
        to={url}
        className="link link-hover inline-flex items-center gap-1 no-underline"
        onClick={(e) => e.stopPropagation()}
      >
        {label}
        <span className="text-xs opacity-50">{indicator}</span>
      </Link>
    </th>
  );
}

interface SortOption {
  value: string;
  label: string;
}

interface MobileSortSelectProps {
  currentSort: string;
  currentOrder: string;
  basePath: string;
  params?: Record<string, string | string[]>;
  options: SortOption[];
}

export function MobileSortSelect({
  currentSort,
  currentOrder,
  basePath,
  params = {},
  options,
}: MobileSortSelectProps) {
  const { t } = useTranslation();
  const currentValue = `${currentSort}:${currentOrder}`;

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const [sort, order] = e.target.value.split(":");
    const url = buildSortUrl(basePath, params, sort, order);
    window.location.href = url;
  };

  return (
    <div className="lg:hidden mb-5">
      <div className="flex items-center gap-2">
        <span className="text-xs opacity-60">{t("common.sort_by")}</span>
        <select
          className="select select-sm flex-1"
          value={currentValue}
          onChange={handleChange}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

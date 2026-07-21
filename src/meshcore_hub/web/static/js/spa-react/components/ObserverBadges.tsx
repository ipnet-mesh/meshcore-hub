import { useTranslation } from "react-i18next";
import { formatNumber, truncateKey, extractFirstEmoji } from "@/utils/format";

interface Observer {
  tag_name?: string;
  name?: string;
  public_key: string;
}

export function ObserverIcons({ observers }: { observers: Observer[] }) {
  if (!observers || observers.length === 0) return null;
  const names = observers.map(
    (o) => o.tag_name || o.name || truncateKey(o.public_key, 8),
  );
  const tooltip = names.join(", ");
  return (
    <span
      className="badge badge-sm badge-primary observer-badge"
      title={tooltip}
    >
      {formatNumber(observers.length)}
    </span>
  );
}

const OBSERVER_FILTER_KEY = "meshcore-observer-areas-disabled";

export function getDisabledObserverAreas(): Set<string> {
  try {
    const raw = localStorage.getItem(OBSERVER_FILTER_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? new Set(arr) : new Set();
  } catch {
    return new Set();
  }
}

export function setDisabledObserverAreas(disabled: Set<string>): void {
  try {
    localStorage.setItem(OBSERVER_FILTER_KEY, JSON.stringify([...disabled]));
  } catch {
    // ignore
  }
}

export function toggleObserverArea(
  area: string,
  totalAreaCount: number,
): Set<string> {
  const disabled = getDisabledObserverAreas();
  if (disabled.has(area)) {
    disabled.delete(area);
  } else {
    if (totalAreaCount - disabled.size <= 1) return disabled;
    disabled.add(area);
  }
  setDisabledObserverAreas(disabled);
  return disabled;
}

interface ObserverFilterBadgesProps {
  areas: string[];
  disabled: Set<string>;
  onToggle: (area: string) => void;
  extraClass?: string;
}

export function ObserverFilterBadges({
  areas,
  disabled,
  onToggle,
  extraClass = "flex",
}: ObserverFilterBadgesProps) {
  const { t } = useTranslation();
  if (!areas || areas.length === 0) return null;

  return (
    <div className={`flex-wrap items-center gap-2 ${extraClass}`}>
      <span className="opacity-80 text-sm">
        {t("common.filter_observer_label")}:
      </span>
      {areas.map((area) => {
        const enabled = !disabled.has(area);
        const cls = enabled
          ? "badge badge-primary"
          : "badge badge-ghost opacity-50";
        const title = enabled
          ? t("common.filter_observer_disable")
          : t("common.filter_observer_enable");
        const emoji = extractFirstEmoji(area);
        const label = emoji ? area.replace(emoji, "").trim() || area : area;
        return (
          <button
            key={area}
            type="button"
            className={`${cls} cursor-pointer`}
            title={title}
            onClick={() => onToggle(area)}
          >
            {emoji && <span className="mr-1">{emoji}</span>}
            {label}
          </button>
        );
      })}
    </div>
  );
}

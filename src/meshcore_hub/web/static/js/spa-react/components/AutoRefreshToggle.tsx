import { useTranslation } from "react-i18next";
import { IconRefresh } from "@/components/icons";

interface AutoRefreshToggleProps {
  paused: boolean;
  onToggle: () => void;
  intervalSeconds: number;
}

export function AutoRefreshToggle({
  paused,
  onToggle,
  intervalSeconds,
}: AutoRefreshToggleProps) {
  const { t } = useTranslation();
  if (intervalSeconds <= 0) return null;
  return (
    <label
      className="label cursor-pointer gap-2"
      title={paused ? t("auto_refresh.resume") : t("auto_refresh.pause")}
    >
      <span className="text-sm opacity-80 flex items-center gap-1">
        <IconRefresh className="w-4 h-4" />
        <span className="text-xs">{intervalSeconds}s</span>
      </span>
      <input
        type="checkbox"
        className="toggle toggle-sm toggle-primary"
        data-testid="auto-refresh-toggle"
        checked={!paused}
        onChange={onToggle}
      />
    </label>
  );
}

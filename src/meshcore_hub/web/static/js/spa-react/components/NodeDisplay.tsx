import { useTranslation } from "react-i18next";
import { getNodeEmoji } from "@/utils/format";

interface NodeDisplayProps {
  name: string | null;
  description?: string | null;
  publicKey: string;
  advType: string | null;
  size?: "sm" | "base";
}

export function NodeDisplay({
  name,
  description,
  publicKey,
  advType,
  size = "base",
}: NodeDisplayProps) {
  const { t } = useTranslation();
  const emoji = getNodeEmoji(name, advType);
  const nameSize = size === "sm" ? "text-sm" : "text-base";

  return (
    <div className="flex items-center gap-2 min-w-0">
      <span
        className="text-lg flex-shrink-0"
        title={advType || t("node_types.unknown")}
      >
        {emoji}
      </span>
      <div className="min-w-0">
        {name ? (
          <>
            <div className={`font-medium ${nameSize} truncate`}>{name}</div>
            {description && (
              <div className="text-xs opacity-70 truncate">{description}</div>
            )}
          </>
        ) : (
          <div className={`font-mono ${nameSize} truncate`}>
            {publicKey.slice(0, 16)}...
          </div>
        )}
      </div>
    </div>
  );
}

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { copyToClipboard } from "@/utils/clipboard";
import { JsonTree } from "@/components/JsonTree";

export { DefinitionField as Field } from "@/components/Definition";

export function RedactedNotice() {
  const { t } = useTranslation();
  return (
    <div className="alert alert-warning mb-4">
      {"\u{1F512}"} {t("packets.redacted_notice")}
    </div>
  );
}

export function channelNameDisplay(
  names: Map<number, string>,
  channelIdx: number | null,
): ReactNode {
  if (channelIdx == null) return <span className="opacity-50">—</span>;
  const name = names.get(channelIdx);
  return name ? `${name} (${channelIdx})` : `${channelIdx}`;
}

export function RawHexBlock({ hex }: { hex: string | null }) {
  const { t } = useTranslation();
  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs uppercase opacity-60">{t("packets.col_raw")}</span>
        {hex && (
          <button
            className="btn btn-xs btn-ghost"
            onClick={(e) => copyToClipboard(e, hex)}
          >
            {t("packets.copy_raw")}
          </button>
        )}
      </div>
      <pre className="bg-base-200 rounded p-3 text-xs overflow-x-auto whitespace-pre-wrap break-all">
        {hex || "—"}
      </pre>
    </div>
  );
}

export function DecodedJsonBlock({ value }: { value: unknown }) {
  const { t } = useTranslation();
  return (
    <div className="mt-4">
      <span className="text-xs uppercase opacity-60">{t("packets.decoded")}</span>
      <div className="bg-base-200 rounded p-3">
        <JsonTree value={value} openDepth={1} />
      </div>
    </div>
  );
}

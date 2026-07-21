import { useAppConfig } from "@/context/AppConfigContext";

export function parseAppDate(isoString: string | null): Date | null {
  if (!isoString || typeof isoString !== "string") return null;

  let value = isoString.trim();
  if (!value) return null;

  if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}/.test(value)) {
    value = value.replace(/\s+/, "T");
  }

  const hasTimePart = /T\d{2}:\d{2}/.test(value);
  const hasTimezoneSuffix = /(Z|[+-]\d{2}:\d{2}|[+-]\d{4})$/i.test(value);
  if (hasTimePart && !hasTimezoneSuffix) {
    value += "Z";
  }

  const parsed = new Date(value);
  if (isNaN(parsed.getTime())) return null;
  return parsed;
}

export function formatNumber(
  value: number | string | null | undefined,
): string {
  if (value === null || value === undefined || value === "") return "";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return new Intl.NumberFormat().format(n);
}

export function useFormatDateTime() {
  const config = useAppConfig();
  const tz = config.timezone_iana || "UTC";
  const locale = config.datetime_locale || "en-US";

  return {
    formatDateTime(
      isoString: string | null,
      options?: Intl.DateTimeFormatOptions,
    ): string {
      if (!isoString) return "-";
      try {
        const date = parseAppDate(isoString);
        if (!date) return "-";
        const opts = options ?? {
          timeZone: tz,
          year: "numeric" as const,
          month: "2-digit" as const,
          day: "2-digit" as const,
          hour: "2-digit" as const,
          minute: "2-digit" as const,
          second: "2-digit" as const,
          hour12: false,
        };
        if (!opts.timeZone) opts.timeZone = tz;
        return date.toLocaleString(locale, opts);
      } catch {
        return isoString ? isoString.slice(0, 19).replace("T", " ") : "-";
      }
    },

    formatDateTimeShort(isoString: string | null): string {
      if (!isoString) return "-";
      try {
        const date = parseAppDate(isoString);
        if (!date) return "-";
        return date.toLocaleString(locale, {
          timeZone: tz,
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        });
      } catch {
        return isoString ? isoString.slice(0, 16).replace("T", " ") : "-";
      }
    },
  };
}

export function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return "";
  const date = parseAppDate(isoString);
  if (!date) return "";
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);
  const t = window.t;
  if (diffDay > 0) return t("time.days_ago", { count: diffDay });
  if (diffHour > 0) return t("time.hours_ago", { count: diffHour });
  if (diffMin > 0) return t("time.minutes_ago", { count: diffMin });
  return t("time.less_than_minute");
}

export function truncateKey(key: string | null, length = 12): string {
  if (!key) return "-";
  if (key.length <= length) return key;
  return key.slice(0, length) + "...";
}

export function resolveNodeName(
  node: {
    name?: string | null;
    public_key?: string | null;
    tags?: { key: string; value: string | null }[];
  } | null | undefined,
  fallbackLength = 12,
): string {
  if (!node) return "-";
  const tagName = node.tags?.find((tag) => tag.key === "name")?.value;
  return (
    tagName || node.name || truncateKey(node.public_key ?? null, fallbackLength)
  );
}

function inferNodeType(value: string | null): string | null {
  const normalized = (value ?? "").toLowerCase();
  if (!normalized) return null;
  if (normalized.includes("room")) return "room";
  if (normalized.includes("repeater") || normalized.includes("relay"))
    return "repeater";
  if (normalized.includes("companion") || normalized.includes("observer"))
    return "companion";
  if (normalized.includes("chat")) return "chat";
  return null;
}

export function typeEmoji(advType: string | null): string {
  switch (inferNodeType(advType) ?? (advType ?? "").toLowerCase()) {
    case "chat":
      return "\u{1F4AC}";
    case "repeater":
      return "\u{1F4E1}";
    case "companion":
      return "\u{1F4F1}";
    case "room":
      return "\u{1FAA7}";
    default:
      return "\u{1F4CD}";
  }
}

export function extractFirstEmoji(str: string | null): string | null {
  if (!str) return null;
  const emojiRegex =
    /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F000}-\u{1F02F}\u{1F0A0}-\u{1F0FF}\u{1F100}-\u{1F64F}\u{1F680}-\u{1F6FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{231A}-\u{231B}\u{23E9}-\u{23FA}\u{25AA}-\u{25AB}\u{25B6}\u{25C0}\u{25FB}-\u{25FE}\u{2B50}\u{2B55}\u{3030}\u{303D}\u{3297}\u{3299}](?:\u{FE0F})?(?:\u{200D}[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}](?:\u{FE0F})?)*|\u{00A9}|\u{00AE}|\u{203C}|\u{2049}|\u{2122}|\u{2139}|\u{2194}-\u{2199}|\u{21A9}-\u{21AA}|\u{24C2}|\u{2934}-\u{2935}|\u{2B05}-\u{2B07}|\u{2B1B}-\u{2B1C}/u;
  const match = str.match(emojiRegex);
  return match ? match[0] : null;
}

export function getNodeEmoji(
  nodeName: string | null,
  advType: string | null,
): string {
  const nameEmoji = extractFirstEmoji(nodeName);
  if (nameEmoji) return nameEmoji;
  const inferred = inferNodeType(advType) ?? inferNodeType(nodeName);
  return typeEmoji(inferred ?? advType);
}

export function getPageColor(name: string): string {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(`--color-${name}`)
    .trim();
}

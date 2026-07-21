import { afterEach, describe, expect, it } from "vitest";

import {
  extractFirstEmoji,
  formatNumber,
  formatRelativeTime,
  getNodeEmoji,
  parseAppDate,
  resolveNodeName,
  truncateKey,
  typeEmoji,
} from "@/utils/format";

const fmt = (n: number) => new Intl.NumberFormat().format(n);

describe("parseAppDate", () => {
  it("returns null for empty/invalid input", () => {
    expect(parseAppDate(null)).toBeNull();
    expect(parseAppDate("")).toBeNull();
    expect(parseAppDate("   ")).toBeNull();
    expect(parseAppDate("not a date")).toBeNull();
  });

  it("treats naive datetimes as UTC", () => {
    const d = parseAppDate("2026-02-08 12:30:00");
    expect(d).not.toBeNull();
    expect(d!.getTime()).toBe(Date.parse("2026-02-08T12:30:00Z"));
  });

  it("preserves explicit timezone offsets", () => {
    const d = parseAppDate("2026-02-08T12:30:00+02:00");
    expect(d!.getTime()).toBe(Date.parse("2026-02-08T12:30:00+02:00"));
  });

  it("parses date-only strings", () => {
    const d = parseAppDate("2026-02-08");
    expect(d).not.toBeNull();
    expect(d!.getTime()).toBe(Date.parse("2026-02-08"));
  });
});

describe("formatNumber", () => {
  it("returns empty string for null/undefined/empty", () => {
    expect(formatNumber(null)).toBe("");
    expect(formatNumber(undefined)).toBe("");
    expect(formatNumber("")).toBe("");
  });

  it("returns the raw string for non-numeric input", () => {
    expect(formatNumber("abc")).toBe("abc");
  });

  it("formats numbers with locale grouping", () => {
    expect(formatNumber(1234)).toBe(fmt(1234));
    expect(formatNumber("1234")).toBe(fmt(1234));
    expect(formatNumber(0)).toBe(fmt(0));
  });
});

describe("truncateKey", () => {
  it("returns '-' for empty input", () => {
    expect(truncateKey(null)).toBe("-");
  });

  it("returns short keys unchanged", () => {
    expect(truncateKey("short")).toBe("short");
  });

  it("truncates long keys with an ellipsis", () => {
    const key = "abcdefghijklmnopqrst";
    expect(truncateKey(key)).toBe("abcdefghijkl...");
    expect(truncateKey(key, 4)).toBe("abcd...");
  });
});

describe("resolveNodeName", () => {
  const key = "0123456789abcdef0123456789abcdef";

  it("returns '-' for null/undefined nodes", () => {
    expect(resolveNodeName(null)).toBe("-");
    expect(resolveNodeName(undefined)).toBe("-");
  });

  it("prefers a 'name' tag value", () => {
    expect(
      resolveNodeName({
        name: "Real Name",
        public_key: key,
        tags: [{ key: "name", value: "Tag Name" }],
      }),
    ).toBe("Tag Name");
  });

  it("falls back to the node name when there is no name tag", () => {
    expect(resolveNodeName({ name: "Real Name", public_key: key })).toBe(
      "Real Name",
    );
  });

  it("falls back to a truncated public key when there is no name", () => {
    expect(resolveNodeName({ name: null, public_key: key })).toBe(
      "0123456789ab...",
    );
    expect(resolveNodeName({ public_key: key })).toBe("0123456789ab...");
  });
});

describe("typeEmoji", () => {
  it("maps node types to emoji (incl. inference from substrings)", () => {
    expect(typeEmoji("chat")).toBe("\u{1F4AC}");
    expect(typeEmoji("repeater")).toBe("\u{1F4E1}");
    expect(typeEmoji("room")).toBe("\u{1FAA7}");
    expect(typeEmoji("companion")).toBe("\u{1F4F1}");
    expect(typeEmoji("Chat Node")).toBe("\u{1F4AC}");
    expect(typeEmoji("My Repeater")).toBe("\u{1F4E1}");
  });

  it("falls back to a pin for unknown/null types", () => {
    expect(typeEmoji(null)).toBe("\u{1F4CD}");
    expect(typeEmoji("sensor")).toBe("\u{1F4CD}");
  });
});

describe("extractFirstEmoji", () => {
  it("returns null when there is no emoji", () => {
    expect(extractFirstEmoji(null)).toBeNull();
    expect(extractFirstEmoji("plain text")).toBeNull();
  });

  it("extracts the first emoji", () => {
    expect(extractFirstEmoji("\u{1F525} hot node")).toBe("\u{1F525}");
  });
});

describe("getNodeEmoji", () => {
  it("prefers an emoji in the node name", () => {
    expect(getNodeEmoji("\u{1F680} Rocket", null)).toBe("\u{1F680}");
  });

  it("infers from type/name when no name emoji", () => {
    expect(getNodeEmoji("Living Room", null)).toBe("\u{1FAA7}");
    expect(getNodeEmoji("X", "repeater")).toBe("\u{1F4E1}");
  });
});

describe("formatRelativeTime", () => {
  afterEach(() => {
    delete (window as { t?: unknown }).t;
  });

  const withT = () => {
    window.t = (key: string) => key;
  };

  const isoAgo = (ms: number) => new Date(Date.now() - ms).toISOString();

  it("returns empty string for empty/invalid input", () => {
    withT();
    expect(formatRelativeTime(null)).toBe("");
  });

  it("buckets elapsed time into relative labels", () => {
    withT();
    expect(formatRelativeTime(isoAgo(10 * 1000))).toBe("time.less_than_minute");
    expect(formatRelativeTime(isoAgo(5 * 60 * 1000))).toBe("time.minutes_ago");
    expect(formatRelativeTime(isoAgo(3 * 60 * 60 * 1000))).toBe("time.hours_ago");
    expect(formatRelativeTime(isoAgo(2 * 24 * 60 * 60 * 1000))).toBe(
      "time.days_ago",
    );
  });
});

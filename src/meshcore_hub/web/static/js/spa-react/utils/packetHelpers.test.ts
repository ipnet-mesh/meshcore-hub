import { describe, expect, it } from "vitest";

import { buildChannelList, packetUrl } from "@/utils/packetHelpers";

describe("buildChannelList", () => {
  it("parses channel_hash hex into a numeric idx", () => {
    const result = buildChannelList([
      { name: "Public", channel_hash: "11" },
      { name: "Custom", channel_hash: "ff" },
    ]);
    expect(result).toEqual([
      { name: "Public", idx: 17 },
      { name: "Custom", idx: 255 },
    ]);
  });

  it("filters out entries with non-hex hashes", () => {
    expect(buildChannelList([{ name: "Bad", channel_hash: "xyz" }])).toEqual([]);
  });
});

describe("packetUrl", () => {
  it("uses the hash route when packet_hash exists", () => {
    expect(packetUrl({ packet_hash: "abc123" })).toBe("/packets/hash/abc123");
  });

  it("falls back to the first reception packet_id", () => {
    expect(
      packetUrl({ receptions: [{ packet_id: "p1" }, { packet_id: "p2" }] }),
    ).toBe("/packets/p1");
  });

  it("falls back to /packets when nothing is available", () => {
    expect(packetUrl({})).toBe("/packets");
  });
});

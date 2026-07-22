import { describe, expect, it } from "vitest";

import { buildChannelNames, isNotFoundError } from "@/utils/packets";

describe("buildChannelNames", () => {
  it("maps hex channel_hash to name by parsed index", () => {
    const names = buildChannelNames([
      { name: "General", channel_hash: "0" },
      { name: "Lobby", channel_hash: "a" },
      { name: "Ops", channel_hash: "ff" },
    ]);
    expect(names.get(0)).toBe("General");
    expect(names.get(10)).toBe("Lobby");
    expect(names.get(255)).toBe("Ops");
  });

  it("skips entries whose hash is not a number", () => {
    const names = buildChannelNames([
      { name: "Bad", channel_hash: "zz" },
      { name: "Good", channel_hash: "1" },
    ]);
    expect(names.size).toBe(1);
    expect(names.get(1)).toBe("Good");
  });

  it("returns an empty map for no items", () => {
    expect(buildChannelNames([]).size).toBe(0);
  });
});

describe("isNotFoundError", () => {
  it("detects 404 in the error message", () => {
    expect(isNotFoundError(new Error("API error: 404 Not Found"))).toBe(true);
  });

  it("returns false for other errors and non-Error values", () => {
    expect(isNotFoundError(new Error("API error: 500"))).toBe(false);
    expect(isNotFoundError("404")).toBe(false);
    expect(isNotFoundError(null)).toBe(false);
  });
});

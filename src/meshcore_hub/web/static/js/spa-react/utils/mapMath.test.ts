import { describe, expect, it } from "vitest";

import {
  getDistanceKm,
  getNodesWithinRadius,
  getAnchorPoint,
  normalizeType,
} from "@/utils/mapMath";

describe("getDistanceKm", () => {
  it("returns 0 for the same point", () => {
    expect(getDistanceKm(10, 20, 10, 20)).toBeCloseTo(0);
  });

  it("calculates distance between two known points", () => {
    const d = getDistanceKm(51.5074, -0.1278, 48.8566, 2.3522);
    expect(d).toBeGreaterThan(330);
    expect(d).toBeLessThan(360);
  });
});

describe("getNodesWithinRadius", () => {
  const nodes = [
    { lat: 0, lon: 0, adv_type: null },
    { lat: 0.01, lon: 0.01, adv_type: null },
    { lat: 10, lon: 10, adv_type: null },
  ];

  it("filters to only nearby nodes", () => {
    expect(getNodesWithinRadius(nodes, 0, 0, 100)).toHaveLength(2);
  });

  it("returns all when the radius is large enough", () => {
    expect(getNodesWithinRadius(nodes, 0, 0, 2000)).toHaveLength(3);
  });
});

describe("getAnchorPoint", () => {
  it("returns the adopted center when provided", () => {
    expect(getAnchorPoint([], { lat: 5, lon: 5 })).toEqual({ lat: 5, lon: 5 });
  });

  it("returns origin for empty nodes with no center", () => {
    expect(getAnchorPoint([], null)).toEqual({ lat: 0, lon: 0 });
  });

  it("computes the centroid of multiple nodes", () => {
    const nodes = [
      { lat: 0, lon: 0, adv_type: null },
      { lat: 10, lon: 20, adv_type: null },
    ];
    expect(getAnchorPoint(nodes, null)).toEqual({ lat: 5, lon: 10 });
  });
});

describe("normalizeType", () => {
  it("lowercases the type string", () => {
    expect(normalizeType("CHAT")).toBe("chat");
  });

  it("returns null for null input", () => {
    expect(normalizeType(null)).toBeNull();
  });
});

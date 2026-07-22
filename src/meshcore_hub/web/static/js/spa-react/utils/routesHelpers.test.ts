import { describe, expect, it } from "vitest";

import {
  qualityOf,
  qualityBadgeClass,
  qualityLabel,
  diagnosisText,
} from "@/utils/routesHelpers";

const t = (key: string) => key;

describe("qualityOf", () => {
  it("prefers quality_avg over route_result", () => {
    expect(
      qualityOf({ quality_avg: "clear", route_result: { quality: "failing" } }),
    ).toBe("clear");
  });

  it("falls back to route_result.quality when quality_avg is empty", () => {
    expect(
      qualityOf({ quality_avg: null, route_result: { quality: "marginal" } }),
    ).toBe("marginal");
  });

  it("returns unknown when neither is available", () => {
    expect(qualityOf({})).toBe("unknown");
  });
});

describe("qualityBadgeClass", () => {
  it("returns neutral when disabled", () => {
    expect(qualityBadgeClass("clear", false)).toBe("badge-neutral");
  });

  it("returns the correct class for each known quality", () => {
    expect(qualityBadgeClass("clear", true)).toBe("badge-success");
    expect(qualityBadgeClass("marginal", true)).toBe("badge-warning");
    expect(qualityBadgeClass("failing", true)).toBe("badge-error");
    expect(qualityBadgeClass("no_coverage", true)).toBe("badge-info");
    expect(qualityBadgeClass("unknown", true)).toBe("badge-ghost");
  });

  it("returns ghost for unmapped qualities", () => {
    expect(qualityBadgeClass("bizarre", true)).toBe("badge-ghost");
  });
});

describe("qualityLabel", () => {
  it("returns the disabled label when not enabled", () => {
    expect(qualityLabel("clear", false, t)).toBe("routes.disabled");
  });

  it("returns the translated label for a known quality", () => {
    expect(qualityLabel("clear", true, t)).toBe("routes.quality_clear");
    expect(qualityLabel("failing", true, t)).toBe("routes.quality_failing");
  });
});

describe("diagnosisText", () => {
  it("returns empty string when there is no route result", () => {
    expect(diagnosisText({ enabled: true }, t)).toBe("");
  });

  it("returns empty string when the route is disabled", () => {
    expect(
      diagnosisText(
        { enabled: false, route_result: { state: "healthy" } },
        t,
      ),
    ).toBe("");
  });

  it("returns the healthy diagnosis", () => {
    expect(
      diagnosisText({ enabled: true, route_result: { state: "healthy" } }, t),
    ).toBe("routes.diagnosis_healthy");
  });

  it("returns the unhealthy diagnosis", () => {
    expect(
      diagnosisText({ enabled: true, route_result: { state: "unhealthy" } }, t),
    ).toBe("routes.diagnosis_unhealthy");
  });

  it("returns the no_coverage diagnosis", () => {
    expect(
      diagnosisText(
        { enabled: true, route_result: { state: "no_coverage" } },
        t,
      ),
    ).toBe("routes.diagnosis_no_coverage");
  });
});

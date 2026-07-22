import { describe, expect, it } from "vitest";

import { groupByObserver } from "@/utils/packetGroupHelpers";

describe("groupByObserver", () => {
  it("groups receptions by observed_by", () => {
    const receptions = [
      { observed_by: "a", snr: 1 },
      { observed_by: "b", snr: 2 },
      { observed_by: "a", snr: 3 },
    ];
    const groups = groupByObserver(receptions);
    expect(groups.size).toBe(2);
    expect(groups.get("a")).toHaveLength(2);
    expect(groups.get("b")).toHaveLength(1);
  });

  it("uses __unknown__ key for null observed_by", () => {
    const groups = groupByObserver([{ observed_by: null }]);
    expect(groups.has("__unknown__")).toBe(true);
  });

  it("returns an empty map for empty input", () => {
    expect(groupByObserver([]).size).toBe(0);
  });
});

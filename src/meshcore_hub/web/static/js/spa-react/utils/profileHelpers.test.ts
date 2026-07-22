import { describe, expect, it } from "vitest";

import { hasOperatorOrAdmin } from "@/utils/profileHelpers";
import { makeConfig } from "@/test/makeConfig";

describe("hasOperatorOrAdmin", () => {
  it("returns true when roles include operator", () => {
    expect(hasOperatorOrAdmin(["operator"], makeConfig())).toBe(true);
  });

  it("returns true when roles include admin", () => {
    expect(hasOperatorOrAdmin(["admin"], makeConfig())).toBe(true);
  });

  it("returns false for member-only roles", () => {
    expect(hasOperatorOrAdmin(["member"], makeConfig())).toBe(false);
  });

  it("returns false for null roles", () => {
    expect(hasOperatorOrAdmin(null, makeConfig())).toBe(false);
  });

  it("respects custom role names from config", () => {
    const config = makeConfig({ role_names: { operator: "netcop" } });
    expect(hasOperatorOrAdmin(["netcop"], config)).toBe(true);
    expect(hasOperatorOrAdmin(["operator"], config)).toBe(false);
  });
});

import { describe, it, expect } from "vitest";
import { displayName } from "@/lib/displayName";

describe("displayName", () => {
  it("falls back for nullish / blank input", () => {
    expect(displayName(null)).toBe("Unknown user");
    expect(displayName(undefined)).toBe("Unknown user");
    expect(displayName("   ")).toBe("Unknown user");
  });
  it("returns the local part of an email (never leaks the domain)", () => {
    expect(displayName("dhoteharshal16@gmail.com")).toBe("dhoteharshal16");
  });
  it("returns a real name untouched", () => {
    expect(displayName("Harshal Dhote")).toBe("Harshal Dhote");
  });
});

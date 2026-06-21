import { describe, it, expect } from "vitest";
import { fmtMs, durationTone } from "@/lib/duration";

describe("fmtMs", () => {
  it("renders an em-dash for nullish / NaN input", () => {
    expect(fmtMs(null)).toBe("—");
    expect(fmtMs(undefined)).toBe("—");
    expect(fmtMs(NaN)).toBe("—");
  });
  it("renders sub-millisecond values in microseconds", () => {
    expect(fmtMs(0.25)).toBe("250 µs");
  });
  it("keeps one decimal for small millisecond values", () => {
    expect(fmtMs(4.2)).toBe("4.2 ms");
  });
  it("rounds larger millisecond values", () => {
    expect(fmtMs(123.6)).toBe("124 ms");
  });
  it("switches to seconds above 1000ms", () => {
    expect(fmtMs(1500)).toBe("1.50 s");
  });
  it("switches to minutes above 60s", () => {
    expect(fmtMs(90_000)).toBe("1 min 30 s");
  });
});

describe("durationTone", () => {
  it("escalates tone with slowness", () => {
    expect(durationTone(null)).toBe("text-slate-500");
    expect(durationTone(50)).toBe("text-slate-300");
    expect(durationTone(200)).toBe("text-sky-300");
    expect(durationTone(2000)).toBe("text-amber-300");
    expect(durationTone(20_000)).toBe("text-red-300");
  });
});

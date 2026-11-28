import { describe, expect, it } from "vitest";
import { costToCredits } from "./credit-rates-store";

const rates = { creditsPerCny: 150, cnyPer: { CNY: 1, USD: 7.2 } };

describe("costToCredits", () => {
  it("converts every currency through CNY with the platform multiplier", () => {
    expect(costToCredits({ CNY: 1.47 }, rates)).toBeCloseTo(220.5);
    expect(costToCredits({ CNY: 1, USD: 0.5 }, rates)).toBeCloseTo((1 + 3.6) * 150);
  });

  it("gives up on a currency it has no rate for", () => {
    expect(costToCredits({ EUR: 1 }, rates)).toBeNull();
  });

  it("is zero for no usage", () => {
    expect(costToCredits({}, rates)).toBe(0);
  });
});

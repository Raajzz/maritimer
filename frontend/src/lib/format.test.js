import { describe, expect, it } from "vitest";

import { decimalSign, formatMoney as fm, formatRate, humanize, statusTone } from "./format";

// Intl uses a non-breaking space after the currency code.
const formatMoney = (...args) => fm(...args).replace(/\u00a0/g, " ");

describe("format helpers", () => {
  it("formats decimal strings without float drift", () => {
    expect(formatMoney("2437.55", "USD")).toBe("USD 2,437.55");
    expect(formatMoney("0.10", "USD")).toBe("USD 0.10");
    expect(formatMoney("-123.94", "USD", { signed: true })).toBe("-USD 123.94");
    expect(formatMoney(null)).toBe("—");
  });

  it("reads the sign of decimal strings", () => {
    expect(decimalSign("-0.00")).toBe(0);
    expect(decimalSign("-1.20")).toBe(-1);
    expect(decimalSign("4.00")).toBe(1);
  });

  it("trims rates", () => {
    expect(formatRate("0.0120100000")).toBe("0.01201");
    expect(formatRate("1.0000000000")).toBe("1");
  });

  it("maps statuses to tones", () => {
    expect(statusTone("SETTLED")).toBe("success");
    expect(statusTone("DISPUTED")).toBe("cta");
    expect(statusTone("DRAFT")).toBe("neutral");
    expect(humanize("PDA_SENT")).toBe("PDA sent");
    expect(humanize("BALANCE_DUE")).toBe("Balance due");
  });
});

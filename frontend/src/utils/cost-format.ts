import type { CostBreakdown, CostByType } from "@/types";

const formatterCache = new Map<string, Intl.NumberFormat>();
const CURRENCY_ORDER = ["CNY", "USD"];
const EMPTY_COST_PLACEHOLDER = "\u2014";
const DEFAULT_FRACTION_DIGITS = 2;

/**
 * SaaS: costs are shown in credits instead of money. Components that format costs call
 * ``useCreditDisplay()`` (stores/credit-rates-store), which registers the rates here before
 * they render; "pending" means credits are expected but the rates are not loaded yet.
 */
export interface CreditDisplayRates {
  creditsPerCny: number;
  cnyPer: Record<string, number>;
  /** "12.5" -> "12.5 积分" in the current language. */
  label: (credits: string) => string;
}
let creditDisplay: CreditDisplayRates | "pending" | null = null;

export function setCreditDisplay(display: CreditDisplayRates | "pending" | null): void {
  creditDisplay = display;
}

function formatCreditsNumber(credits: number): string {
  return credits.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** Credits for one amount, or null when it should stay money (no rate for the currency). */
function creditsFor(display: CreditDisplayRates, currency: string, amount: number): number | null {
  const per = display.cnyPer[currency];
  if (per === undefined || !Number.isFinite(per)) return null;
  const credits = amount * per * display.creditsPerCny;
  return Number.isFinite(credits) ? credits : null;
}

interface CurrencyFormatOptions {
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
}

function getFormatter(
  currency: string,
  minimumFractionDigits: number,
  maximumFractionDigits: number,
): Intl.NumberFormat {
  const cacheKey = `${currency}:${minimumFractionDigits}:${maximumFractionDigits}`;
  let fmt = formatterCache.get(cacheKey);
  if (!fmt) {
    fmt = new Intl.NumberFormat("en", {
      style: "currency",
      currency,
      currencyDisplay: "symbol",
      minimumFractionDigits,
      maximumFractionDigits,
    });
    formatterCache.set(cacheKey, fmt);
  }
  return fmt;
}

export function costEntries(breakdown: CostBreakdown | undefined): [string, number][] {
  return Object.entries(breakdown ?? {})
    .filter(([, amount]) => amount > 0)
    .sort(([left], [right]) => {
      const leftIndex = CURRENCY_ORDER.indexOf(left);
      const rightIndex = CURRENCY_ORDER.indexOf(right);
      if (leftIndex !== -1 || rightIndex !== -1) {
        return (leftIndex === -1 ? CURRENCY_ORDER.length : leftIndex) -
          (rightIndex === -1 ? CURRENCY_ORDER.length : rightIndex);
      }
      return left.localeCompare(right);
    });
}

export function formatCurrencyAmount(
  currency: string,
  amount: number,
  options: CurrencyFormatOptions = {},
): string {
  if (creditDisplay === "pending") return EMPTY_COST_PLACEHOLDER;
  if (creditDisplay) {
    const credits = creditsFor(creditDisplay, currency, amount);
    if (credits !== null) return creditDisplay.label(formatCreditsNumber(credits));
  }
  const minimumFractionDigits = options.minimumFractionDigits ?? DEFAULT_FRACTION_DIGITS;
  const maximumFractionDigits = options.maximumFractionDigits ?? DEFAULT_FRACTION_DIGITS;
  const normalizedMinimumFractionDigits = Math.min(minimumFractionDigits, maximumFractionDigits);
  const normalizedMaximumFractionDigits = Math.max(minimumFractionDigits, maximumFractionDigits);

  try {
    return getFormatter(currency, normalizedMinimumFractionDigits, normalizedMaximumFractionDigits).format(amount);
  } catch {
    return `${currency} ${amount.toLocaleString("en", {
      minimumFractionDigits: normalizedMinimumFractionDigits,
      maximumFractionDigits: normalizedMaximumFractionDigits,
    })}`;
  }
}

export function formatCost(breakdown: CostBreakdown | undefined): string {
  const entries = costEntries(breakdown);
  if (entries.length === 0 || creditDisplay === "pending") return EMPTY_COST_PLACEHOLDER;
  if (creditDisplay) {
    const display = creditDisplay;
    const parts = entries.map(([cur, amt]) => creditsFor(display, cur, amt));
    if (parts.every((c) => c !== null)) {
      return display.label(formatCreditsNumber(parts.reduce<number>((sum, c) => sum + (c ?? 0), 0)));
    }
  }
  return entries.map(([cur, amt]) => formatCurrencyAmount(cur, amt)).join(" + ");
}

export function formatCostTotal(breakdown: CostBreakdown | undefined, complete: boolean): string {
  if (costEntries(breakdown).length > 0) return formatCost(breakdown);
  if (!complete || creditDisplay === "pending") return EMPTY_COST_PLACEHOLDER;
  return creditDisplay ? creditDisplay.label("0") : "0";
}

export function formatCostOrZero(breakdown: CostBreakdown | undefined): string {
  return formatCost(breakdown);
}

export function currentScriptBreakdown(byType: CostByType): CostBreakdown {
  const withoutHistory: CostByType = { ...byType };
  delete withoutHistory.unassigned;
  return totalBreakdown(withoutHistory);
}

export function totalBreakdown(byType: CostByType): CostBreakdown {
  const result: CostBreakdown = {};
  for (const costs of Object.values(byType) as (CostBreakdown | undefined)[]) {
    if (!costs) continue;
    for (const [cur, amt] of Object.entries(costs)) {
      result[cur] = (result[cur] ?? 0) + amt;
    }
  }
  for (const cur of Object.keys(result)) {
    result[cur] = Math.round(result[cur] * 10000) / 10000;
  }
  return result;
}

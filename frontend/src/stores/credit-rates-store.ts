import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { create } from "zustand";
import { API } from "@/api";
import { useAuthStore } from "@/stores/auth-store";
import { readSaasHint, useIsSaas } from "@/stores/saas-role-store";
import { setCreditDisplay } from "@/utils/cost-format";
import type { CostBreakdown } from "@/types";

/**
 * SaaS: show usage in credits instead of money, with the rates the platform charges with
 * (cost × CNY rate × credits per yuan × cost multiplier, from the control plane).
 */
interface CreditRates {
  creditsPerCny: number;
  cnyPer: Record<string, number>;
}

interface CreditRatesState {
  rates: CreditRates | null;
  loading: boolean;
  /** The last load failed: costs fall back to money instead of staying blank. */
  failed: boolean;
  load: () => Promise<void>;
}

export const useCreditRatesStore = create<CreditRatesState>((set, get) => ({
  rates: null,
  loading: false,
  failed: false,
  load: async () => {
    if (get().loading || get().rates) return;
    set({ loading: true });
    try {
      const raw = await API.request<{ credits_per_cny: string; cny_per: Record<string, string> }>("/saas/credit-rates");
      const cnyPer = Object.fromEntries(
        Object.entries(raw.cny_per).map(([code, value]) => [code, Number(value)]),
      );
      set({ rates: { creditsPerCny: Number(raw.credits_per_cny), cnyPer }, loading: false, failed: false });
    } catch {
      set({ loading: false, failed: true }); // no rates: callers keep showing money
    }
  },
}));

/** Credits for a cost breakdown; null when a currency in it has no rate. */
export function costToCredits(breakdown: CostBreakdown | undefined, rates: CreditRates): number | null {
  let cny = 0;
  for (const [currency, amount] of Object.entries(breakdown ?? {})) {
    if (!amount) continue;
    const per = rates.cnyPer[currency];
    if (per === undefined || !Number.isFinite(per)) return null;
    cny += amount * per;
  }
  const credits = cny * rates.creditsPerCny;
  return Number.isFinite(credits) ? credits : null;
}

export function formatCredits(credits: number): string {
  return credits.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** SaaS: the breakdown in credits ("12.5"), else null (self-hosted, rates not loaded, or unknown currency). */
export function useCostInCredits(breakdown: CostBreakdown | undefined): string | null {
  const saas = useIsSaas();
  const rates = useCreditRatesStore((s) => s.rates);
  const load = useCreditRatesStore((s) => s.load);
  useEffect(() => {
    if (saas && !rates) void load();
  }, [saas, rates, load]);
  if (!saas || !rates) return null;
  const credits = costToCredits(breakdown, rates);
  return credits === null ? null : formatCredits(credits);
}

/**
 * SaaS: show every cost the component formats (formatCost / formatCurrencyAmount) in credits.
 * Call it at the top of each component that formats costs: it registers the rates with
 * utils/cost-format before the component renders and re-renders it once the rates arrive.
 * While SaaS is expected but the rates are still loading, costs show "—" rather than money.
 */
export function useCreditDisplay(): void {
  const { t } = useTranslation("dashboard");
  const token = useAuthStore((s) => s.token);
  const saas = useIsSaas();
  const rates = useCreditRatesStore((s) => s.rates);
  const failed = useCreditRatesStore((s) => s.failed);
  const load = useCreditRatesStore((s) => s.load);
  useEffect(() => {
    if (saas && !rates && !failed) void load();
  }, [saas, rates, failed, load]);
  const expected = Boolean(token) && (saas || readSaasHint());
  if (!expected || failed) {
    setCreditDisplay(null);
  } else if (!rates) {
    setCreditDisplay("pending");
  } else {
    setCreditDisplay({
      ...rates,
      label: (credits) => t("credits_balance_badge", { balance: credits, defaultValue: `${credits} credits` }),
    });
  }
}

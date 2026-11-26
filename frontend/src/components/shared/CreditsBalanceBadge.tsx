import { useEffect, useState } from "react";
import { Coins } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useCreditsBalanceStore } from "@/stores/credits-balance-store";
import { RechargeDialog } from "@/components/shared/RechargeDialog";

function formatCredits(raw: string | null): string {
  if (raw == null || raw === "") return "—";
  const n = Number(raw);
  if (!Number.isFinite(n)) return raw;
  if (Number.isInteger(n)) return String(n);
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatYuan(raw: string | null): string | null {
  if (raw == null || raw === "") return null;
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  return `¥${n.toFixed(2)}`;
}

/** SaaS 顶栏余额：以人民币显示，积分在提示里；自托管不渲染。 */
export function CreditsBalanceBadge() {
  const { t } = useTranslation(["dashboard", "common"]);
  const enabled = useCreditsBalanceStore((s) => s.enabled);
  const balance = useCreditsBalanceStore((s) => s.balance);
  const held = useCreditsBalanceStore((s) => s.held);
  const balanceCny = useCreditsBalanceStore((s) => s.balanceCny);
  const heldCny = useCreditsBalanceStore((s) => s.heldCny);
  const loading = useCreditsBalanceStore((s) => s.loading);
  const refresh = useCreditsBalanceStore((s) => s.refresh);
  const [rechargeOpen, setRechargeOpen] = useState(false);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 60_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  if (!enabled && !loading) return null;

  const creditsText = formatCredits(balance);
  const heldCreditsText = formatCredits(held);
  // Money is shown in CNY; fall back to credits only when the rate is unknown.
  const balanceText = formatYuan(balanceCny) ?? creditsText;
  const heldText = formatYuan(heldCny) ?? heldCreditsText;
  const label = t("dashboard:credits_balance_aria", {
    balance: balanceText,
    held: heldText,
    credits: creditsText,
    defaultValue: `Balance ${balanceText}, held ${heldText}`,
  });

  return (
    <>
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="outline"
              size="sm"
              aria-label={label}
              className="gap-1.5"
              onClick={() => setRechargeOpen(true)}
            />
          }
        >
          <Coins aria-hidden data-icon="inline-start" className="text-muted-foreground" />
          <span className="num">{loading && balance == null ? "…" : balanceText}</span>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          {t("dashboard:credits_balance_tooltip", {
            balance: balanceText,
            held: heldText,
            credits: creditsText,
            defaultValue: `Available ${balanceText} (${creditsText} credits) · Held ${heldText}`,
          })}
        </TooltipContent>
      </Tooltip>
      <RechargeDialog open={rechargeOpen} onClose={() => setRechargeOpen(false)} />
    </>
  );
}

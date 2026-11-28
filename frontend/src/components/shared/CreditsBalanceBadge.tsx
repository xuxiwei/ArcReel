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
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** SaaS 顶栏余额：只显示积分（人民币只在充值时出现）；自托管不渲染。 */
export function CreditsBalanceBadge() {
  const { t } = useTranslation(["dashboard", "common"]);
  const enabled = useCreditsBalanceStore((s) => s.enabled);
  const balance = useCreditsBalanceStore((s) => s.balance);
  const held = useCreditsBalanceStore((s) => s.held);
  const loading = useCreditsBalanceStore((s) => s.loading);
  const refresh = useCreditsBalanceStore((s) => s.refresh);
  const [rechargeOpen, setRechargeOpen] = useState(false);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 60_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  if (!enabled && !loading) return null;

  const balanceText = formatCredits(balance);
  const heldText = formatCredits(held);
  const label = t("dashboard:credits_balance_aria", {
    balance: balanceText,
    held: heldText,
    defaultValue: `Balance ${balanceText} credits, held ${heldText} credits`,
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
          <span className="num">
            {loading && balance == null
              ? "…"
              : t("dashboard:credits_balance_badge", { balance: balanceText, defaultValue: `${balanceText} credits` })}
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          {t("dashboard:credits_balance_tooltip", {
            balance: balanceText,
            held: heldText,
            defaultValue: `Available ${balanceText} credits · Held ${heldText} credits`,
          })}
        </TooltipContent>
      </Tooltip>
      <RechargeDialog open={rechargeOpen} onClose={() => setRechargeOpen(false)} />
    </>
  );
}

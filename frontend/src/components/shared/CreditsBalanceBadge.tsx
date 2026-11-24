import { useEffect } from "react";
import { Coins } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useCreditsBalanceStore } from "@/stores/credits-balance-store";

function formatCredits(raw: string | null): string {
  if (raw == null || raw === "") return "—";
  const n = Number(raw);
  if (!Number.isFinite(n)) return raw;
  if (Number.isInteger(n)) return String(n);
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** SaaS 顶栏积分余额；自托管不渲染。 */
export function CreditsBalanceBadge() {
  const { t } = useTranslation(["dashboard", "common"]);
  const enabled = useCreditsBalanceStore((s) => s.enabled);
  const balance = useCreditsBalanceStore((s) => s.balance);
  const held = useCreditsBalanceStore((s) => s.held);
  const loading = useCreditsBalanceStore((s) => s.loading);
  const refresh = useCreditsBalanceStore((s) => s.refresh);

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
    defaultValue: `Credits ${balanceText}, held ${heldText}`,
  });

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            aria-label={label}
            className="gap-1.5"
            onClick={() => void refresh()}
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
          defaultValue: `Available ${balanceText} · Held ${heldText}`,
        })}
      </TooltipContent>
    </Tooltip>
  );
}

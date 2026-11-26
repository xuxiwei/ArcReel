import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { CheckCircle2, ExternalLink, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { API, type RechargeChannel, type RechargeOptions, type RechargeOrder } from "@/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreditsBalanceStore } from "@/stores/credits-balance-store";
import { errMsg } from "@/utils/async";

const POLL_MS = 3000;

function yuan(raw: string | number): string {
  const n = Number(raw);
  return Number.isFinite(n) ? `¥${n.toFixed(2)}` : String(raw);
}

/** SaaS 充值：选金额（档位或自定义）+ 渠道 → 微信扫码 / 支付宝新窗口支付，轮询到账。 */
export function RechargeDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation(["dashboard", "common"]);
  const formId = useId();
  const amountId = useId();
  const refreshBalance = useCreditsBalanceStore((s) => s.refresh);

  const [options, setOptions] = useState<RechargeOptions | null>(null);
  const [amount, setAmount] = useState("");
  const [channel, setChannel] = useState<RechargeChannel | null>(null);
  const [order, setOrder] = useState<RechargeOrder | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    if (!open) return;
    setOrder(null);
    setError(null);
    API.getRechargeOptions()
      .then((opts) => {
        setOptions(opts);
        setAmount((prev) => prev || opts.tiers[0] || "");
        setChannel((prev) => prev ?? opts.channels[0] ?? null);
      })
      .catch((err) => setError(errMsg(err)));
  }, [open]);

  const orderNo = order?.order_no ?? null;
  const orderStatus = order?.status ?? null;
  useEffect(() => {
    if (!open || !orderNo || orderStatus !== "pending") return;
    const controller = new AbortController();
    const tick = async () => {
      try {
        const next = await API.getRechargeOrder(orderNo, { signal: controller.signal });
        setOrder((prev) => (prev ? { ...prev, ...next } : next));
        if (next.status === "paid") void refreshBalance();
      } catch {
        /* transient; keep polling until expiry */
      }
    };
    pollRef.current = window.setInterval(() => void tick(), POLL_MS);
    return () => {
      controller.abort();
      if (pollRef.current != null) window.clearInterval(pollRef.current);
    };
  }, [open, orderNo, orderStatus, refreshBalance]);

  const amountNum = Number(amount);
  const min = Number(options?.min_cny ?? 0);
  const max = Number(options?.max_cny ?? 0);
  const amountValid =
    Number.isFinite(amountNum) && /^\d+(\.\d{1,2})?$/.test(amount.trim()) && amountNum >= min && amountNum <= max;
  const credits = options && amountValid ? amountNum * Number(options.credits_per_cny) : null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!channel || !amountValid || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await API.createRechargeOrder({ amount_cny: amount.trim(), channel });
      setOrder(created);
      if (created.channel === "alipay" && created.pay_url) {
        window.open(created.pay_url, "_blank", "noopener,noreferrer");
      }
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setSubmitting(false);
    }
  };

  const channelLabel = (c: RechargeChannel) =>
    c === "wechat"
      ? t("dashboard:recharge_channel_wechat", { defaultValue: "WeChat Pay" })
      : t("dashboard:recharge_channel_alipay", { defaultValue: "Alipay" });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !submitting) onClose();
      }}
    >
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>{t("dashboard:recharge_title", { defaultValue: "Top up" })}</DialogTitle>
          <DialogDescription>
            {options
              ? t("dashboard:recharge_desc", {
                  rate: options.credits_per_cny,
                  defaultValue: `¥1 = ${options.credits_per_cny} credits`,
                })
              : null}
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          {order ? (
            <RechargeOrderPanel order={order} channelLabel={channelLabel(order.channel)} />
          ) : (
            <form id={formId} className="flex flex-col gap-4" onSubmit={(event) => void submit(event)}>
              {options && options.channels.length === 0 && (
                <p role="alert" className="text-sm text-destructive">
                  {t("dashboard:recharge_no_channel", { defaultValue: "Online payment is not available yet." })}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                {options?.tiers.map((tier) => (
                  <Button
                    key={tier}
                    type="button"
                    size="sm"
                    variant={Number(tier) === amountNum ? "default" : "outline"}
                    onClick={() => setAmount(String(Number(tier)))}
                  >
                    {yuan(tier)}
                  </Button>
                ))}
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={amountId}>
                  {t("dashboard:recharge_custom", {
                    min: options?.min_cny ?? "",
                    max: options?.max_cny ?? "",
                    defaultValue: `Custom amount (¥${options?.min_cny ?? ""}–¥${options?.max_cny ?? ""})`,
                  })}
                </Label>
                <Input
                  id={amountId}
                  inputMode="decimal"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  aria-invalid={amount !== "" && !amountValid}
                />
                {credits != null && (
                  <p className="text-sm text-muted-foreground">
                    {t("dashboard:recharge_credits_preview", {
                      credits: credits.toLocaleString(undefined, { maximumFractionDigits: 2 }),
                      defaultValue: `You will receive ${credits} credits`,
                    })}
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                {options?.channels.map((c) => (
                  <Button
                    key={c}
                    type="button"
                    size="sm"
                    variant={c === channel ? "default" : "outline"}
                    onClick={() => setChannel(c)}
                  >
                    {channelLabel(c)}
                  </Button>
                ))}
              </div>
            </form>
          )}
          {error && (
            <p role="alert" className="mt-2 text-sm text-destructive">
              {error}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          {order ? (
            <Button variant="outline" onClick={onClose}>
              {t("common:close", { defaultValue: "Close" })}
            </Button>
          ) : (
            <>
              <Button variant="outline" disabled={submitting} onClick={onClose}>
                {t("common:cancel")}
              </Button>
              <Button type="submit" form={formId} disabled={!amountValid || !channel || submitting}>
                {submitting && <Loader2 data-icon="inline-start" className="animate-spin" aria-hidden />}
                {t("dashboard:recharge_pay", {
                  amount: amountValid ? yuan(amountNum) : "",
                  defaultValue: `Pay ${amountValid ? yuan(amountNum) : ""}`,
                })}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RechargeOrderPanel({ order, channelLabel }: { order: RechargeOrder; channelLabel: string }) {
  const { t } = useTranslation(["dashboard"]);
  if (order.status === "paid" || order.status === "partially_refunded" || order.status === "refunded") {
    return (
      <div className="flex flex-col items-center gap-2 py-4 text-center">
        <CheckCircle2 className="size-10 text-primary" aria-hidden />
        <p className="font-medium">
          {t("dashboard:recharge_paid", {
            amount: yuan(order.amount_cny),
            credits: Number(order.credits).toLocaleString(undefined, { maximumFractionDigits: 2 }),
            defaultValue: `Paid ${yuan(order.amount_cny)}, ${order.credits} credits added`,
          })}
        </p>
      </div>
    );
  }
  if (order.status === "closed") {
    return (
      <p role="alert" className="py-4 text-center text-sm text-destructive">
        {t("dashboard:recharge_closed", { defaultValue: "This order has expired. Please create a new one." })}
      </p>
    );
  }
  return (
    <div className="flex flex-col items-center gap-3 py-2 text-center">
      <p className="text-sm text-muted-foreground">
        {t("dashboard:recharge_waiting", {
          channel: channelLabel,
          amount: yuan(order.amount_cny),
          defaultValue: `Pay ${yuan(order.amount_cny)} with ${channelLabel}`,
        })}
      </p>
      {order.channel === "wechat" ? (
        order.qr_svg ? (
          <img src={order.qr_svg} alt={channelLabel} className="size-48 rounded-md border bg-white p-2" />
        ) : (
          <code className="break-all text-xs">{order.pay_url}</code>
        )
      ) : (
        order.pay_url && (
          <Button variant="outline" size="sm" onClick={() => window.open(order.pay_url!, "_blank", "noopener,noreferrer")}>
            <ExternalLink data-icon="inline-start" aria-hidden />
            {t("dashboard:recharge_open_alipay", { defaultValue: "Open Alipay payment page" })}
          </Button>
        )
      )}
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="size-3 animate-spin" aria-hidden />
        {t("dashboard:recharge_polling", { defaultValue: "Waiting for payment confirmation…" })}
      </p>
    </div>
  );
}

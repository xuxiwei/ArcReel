import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, ChevronRight, Loader2, RefreshCcw, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { API, type ReconciliationReport, type ReconciliationReportBrief } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/** SaaS platform admins: the control plane's daily reconciliation reports (internal checks + channel bills). */
export function ReconciliationSection() {
  const { t } = useTranslation(["dashboard", "common"]);
  const [items, setItems] = useState<ReconciliationReportBrief[] | null>(null);
  const [selected, setSelected] = useState<ReconciliationReport | null>(null);
  const [busy, setBusy] = useState<"list" | "internal" | "statements" | "detail" | null>("list");
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );

  const load = useCallback(async () => {
    setBusy("list");
    setError(null);
    try {
      const page = await API.getReconciliationReports(60);
      if (mounted.current) setItems(page.items);
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (mounted.current) setBusy(null);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- mount 后异步拉取报告列表
    void load();
  }, [load]);

  const open = useCallback(async (reportDate: string) => {
    setBusy("detail");
    setError(null);
    try {
      const report = await API.getReconciliationReport(reportDate);
      if (mounted.current) setSelected(report);
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (mounted.current) setBusy(null);
    }
  }, []);

  const run = useCallback(
    async (kind: "internal" | "statements") => {
      setBusy(kind);
      setError(null);
      try {
        const report = await API.runReconciliation(kind, selected?.report_date);
        if (!mounted.current) return;
        setSelected(report);
        await load();
      } catch (err) {
        if (mounted.current) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (mounted.current) setBusy(null);
      }
    },
    [load, selected?.report_date],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold">{t("reconciliation_title")}</h2>
        <p className="text-sm text-muted-foreground">{t("reconciliation_desc")}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" disabled={busy !== null} onClick={() => void run("internal")}>
          {busy === "internal" ? <Loader2 aria-hidden className="animate-spin" /> : <RefreshCcw aria-hidden />}
          {selected ? t("reconciliation_rerun_day", { date: selected.report_date }) : t("reconciliation_run_yesterday")}
        </Button>
        <Button variant="outline" size="sm" disabled={busy !== null} onClick={() => void run("statements")}>
          {busy === "statements" ? <Loader2 aria-hidden className="animate-spin" /> : <RefreshCcw aria-hidden />}
          {t("reconciliation_run_statements")}
        </Button>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {busy === "list" && items === null ? (
        <Loader2 aria-hidden className="size-4 animate-spin text-muted-foreground" />
      ) : items && items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("reconciliation_empty")}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border rounded-lg border border-border">
          {(items ?? []).map((item) => (
            <li key={item.report_date}>
              <button
                type="button"
                className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-muted"
                onClick={() => void open(item.report_date)}
              >
                {item.status === "ok" ? (
                  <CheckCircle2 aria-hidden className="size-4 text-good" />
                ) : (
                  <TriangleAlert aria-hidden className="size-4 text-warn" />
                )}
                <span className="font-mono">{item.report_date}</span>
                <span className="flex flex-1 flex-wrap gap-1">
                  {item.status === "ok" ? (
                    <Badge variant="secondary">{t("reconciliation_ok")}</Badge>
                  ) : (
                    Object.entries(item.issue_counts).map(([check, count]) => (
                      <Badge key={check} variant="outline">
                        {t(`reconciliation_check_${check}`, { defaultValue: check })} × {count}
                      </Badge>
                    ))
                  )}
                </span>
                <ChevronRight aria-hidden className="size-4 text-muted-foreground" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {selected && <ReportDetail report={selected} />}
    </div>
  );
}

function ReportDetail({ report }: { report: ReconciliationReport }) {
  const { t } = useTranslation("dashboard");
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border p-3" aria-label={report.report_date}>
      <h3 className="text-sm font-semibold">{t("reconciliation_detail_title", { date: report.report_date })}</h3>
      <pre className="max-h-64 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(report.summary, null, 2)}</pre>
      {report.issues.length === 0 ? (
        <p className="text-sm text-good">{t("reconciliation_ok")}</p>
      ) : (
        report.issues.map((issue) => (
          <div key={issue.check} className="flex flex-col gap-1">
            <p className="text-sm font-medium">
              {t(`reconciliation_check_${issue.check}`, { defaultValue: issue.check })} × {issue.count}
              {issue.truncated ? ` (${t("reconciliation_truncated")})` : ""}
            </p>
            <pre className="max-h-48 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(issue.items, null, 2)}</pre>
          </div>
        ))
      )}
    </section>
  );
}

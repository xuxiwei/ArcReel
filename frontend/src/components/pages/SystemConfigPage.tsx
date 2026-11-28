import { useCallback, useEffect, useMemo } from "react";
import { useSearch } from "wouter";
import {
  AlertTriangle,
  BarChart3,
  Bot,
  Brain,
  Cable,
  Film,
  HardDrive,
  Info,
  KeyRound,
  Plug,
  ScrollText,
  ShieldCheck,
  SlidersHorizontal,
  Store,
  Waypoints,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { SETTINGS_SECTIONS, settingsSectionPath, type SettingsSection } from "@/app-routes";
import { AgentMemorySection } from "@/components/agent-memory/AgentMemorySection";
import { PageHeader } from "@/components/shared/page-shell/PageHeader";
import { PageShell, type ContainerTier } from "@/components/shared/page-shell/PageShell";
import { PageSidebar, type PageSidebarGroup } from "@/components/shared/page-shell/PageSidebar";
import { useReturnTo } from "@/components/shared/page-shell/return-to";
import { ONBOARDING_ANCHORS } from "@/onboarding/anchors";
import { useConfigStatusStore, useSectionConfigIssues } from "@/stores/config-status-store";
import { useIsRestrictedMember, useIsSaas, useIsSaasAdmin } from "@/stores/saas-role-store";
import { UsageRecordsSection } from "../usage/UsageRecordsSection";
import { AgentConfigTab } from "./AgentConfigTab";
import { ProviderSection } from "./ProviderSection";
import { AboutSection } from "./settings/AboutSection";
import { AssetLibrarySection } from "./settings/asset-library/AssetLibrarySection";
import { AccessTokensSection } from "./settings/agent-access/AccessTokensSection";
import { ExternalAgentSection } from "./settings/agent-access/ExternalAgentSection";
import { ConfigIssueNotice } from "./settings/ConfigIssueNotice";
import { EndpointsSection } from "./settings/endpoints/EndpointsSection";
import { GeneralSection } from "./settings/GeneralSection";
import { MarketSection } from "./settings/market/MarketSection";
import { MediaModelSection } from "./settings/MediaModelSection";
import { PromptTemplatesSection } from "./settings/PromptTemplatesSection";
import { ReconciliationSection } from "./settings/ReconciliationSection";

interface SectionDef {
  labelKey: string;
  icon: LucideIcon;
  tier: ContainerTier;
}

const SECTIONS: Record<SettingsSection, SectionDef> = {
  providers: { labelKey: "dashboard:providers", icon: Plug, tier: "bleed" },
  "default-models": { labelKey: "dashboard:settings_default_models", icon: Film, tier: "constrained" },
  endpoints: { labelKey: "dashboard:ce_section_title", icon: Waypoints, tier: "bleed" },
  "asset-library": { labelKey: "dashboard:settings_asset_library", icon: HardDrive, tier: "constrained" },
  "arcreel-agent": { labelKey: "dashboard:settings_arcreel_agent", icon: Bot, tier: "constrained" },
  "agent-memory": { labelKey: "dashboard:settings_agent_memory", icon: Brain, tier: "bleed" },
  "external-agent": { labelKey: "dashboard:settings_external_agent", icon: Cable, tier: "constrained" },
  "access-tokens": { labelKey: "dashboard:settings_access_tokens", icon: KeyRound, tier: "constrained" },
  market: { labelKey: "dashboard:market_section_title", icon: Store, tier: "full" },
  usage: { labelKey: "dashboard:usage", icon: BarChart3, tier: "full" },
  reconciliation: { labelKey: "dashboard:reconciliation_title", icon: ShieldCheck, tier: "constrained" },
  general: { labelKey: "dashboard:settings_general", icon: SlidersHorizontal, tier: "constrained" },
  "prompt-templates": { labelKey: "dashboard:prompt_templates", icon: ScrollText, tier: "constrained" },
  about: { labelKey: "dashboard:about", icon: Info, tier: "constrained" },
};

const SECTION_GROUPS: { id: string; labelKey?: string; sections: SettingsSection[] }[] = [
  { id: "generation", labelKey: "dashboard:settings_group_generation", sections: ["providers", "default-models", "endpoints", "asset-library"] },
  {
    id: "agent",
    labelKey: "dashboard:settings_group_agent",
    sections: ["arcreel-agent", "agent-memory", "external-agent", "access-tokens"],
  },
  { id: "standalone", sections: ["market", "usage", "reconciliation"] },
  { id: "system", labelKey: "dashboard:settings_group_system", sections: ["general", "prompt-templates", "about"] },
];

const SECTION_ONBOARDING_ANCHORS: Partial<Record<SettingsSection, string>> = {
  providers: ONBOARDING_ANCHORS.settingsProviders,
  "arcreel-agent": ONBOARDING_ANCHORS.settingsAgent,
};

/** SaaS members only see their own settings (usage is scoped to their own calls); the rest is admin-only. */
const MEMBER_SECTIONS: ReadonlySet<SettingsSection> = new Set<SettingsSection>([
  "agent-memory",
  "usage",
  "general",
  "prompt-templates",
  "about",
]);

/**
 * SaaS: platform settings that now live in the control-plane admin console (``arcreel-control-plane/web``).
 * Providers, endpoints, the ArcReel Agent and the market stay here until they are ported.
 */
const MOVED_TO_CONSOLE: ReadonlySet<SettingsSection> = new Set<SettingsSection>([
  "default-models",
  "asset-library",
  "external-agent",
  "access-tokens",
  "reconciliation",
]);
const ADMIN_CONSOLE_URL: string = (import.meta.env.VITE_ADMIN_CONSOLE_URL as string | undefined) ?? "";

function parseSection(search: string): SettingsSection {
  const value = new URLSearchParams(search).get("section");
  return SETTINGS_SECTIONS.find((section) => section === value) ?? "providers";
}

export function SystemConfigPage() {
  const { t } = useTranslation(["common", "dashboard"]);
  const search = useSearch();
  const restricted = useIsRestrictedMember();
  const saasAdmin = useIsSaasAdmin();
  const saas = useIsSaas();
  const visible = useCallback(
    (id: SettingsSection) => {
      if (saas && MOVED_TO_CONSOLE.has(id)) return false;
      if (id === "reconciliation") return saasAdmin;
      return !restricted || MEMBER_SECTIONS.has(id);
    },
    [restricted, saasAdmin, saas],
  );
  const requestedSection = parseSection(search);
  const activeSection: SettingsSection = visible(requestedSection)
    ? requestedSection
    : restricted
      ? "general"
      : "providers";
  const goBack = useReturnTo();

  const configIssues = useSectionConfigIssues();
  const fetchConfigStatus = useConfigStatusStore((s) => s.fetch);

  useEffect(() => {
    void fetchConfigStatus();
  }, [fetchConfigStatus]);

  const issueSections = useMemo(() => new Set(configIssues.map((issue) => issue.section)), [configIssues]);
  const activeIssues = useMemo(
    () => configIssues.filter((issue) => issue.section === activeSection),
    [configIssues, activeSection],
  );
  const groups = useMemo<PageSidebarGroup[]>(
    () =>
      SECTION_GROUPS.map((group) => ({
        id: group.id,
        label: group.labelKey ? t(group.labelKey) : undefined,
        items: group.sections.filter(visible).map((id) => ({
          id,
          label: t(SECTIONS[id].labelKey),
          icon: SECTIONS[id].icon,
          href: settingsSectionPath(id),
          onboardingAnchor: SECTION_ONBOARDING_ANCHORS[id],
          badge:
            issueSections.has(id) ? (
              <span role="img" aria-label={t("dashboard:config_incomplete")} className="text-warn">
                <AlertTriangle aria-hidden className="size-3.5" />
              </span>
            ) : undefined,
        })),
      })).filter((group) => group.items.length > 0),
    [t, issueSections, visible],
  );

  return (
    <PageShell
      header={<PageHeader back={{ label: t("common:back"), onClick: goBack }} title={t("common:settings")} />}
      sidebar={<PageSidebar label={t("common:settings")} groups={groups} activeId={activeSection} replace />}
      tier={SECTIONS[activeSection].tier}
    >
      {SECTIONS[activeSection].tier === "bleed" && activeIssues.length > 0 && (
        <div className="shrink-0 px-6 pt-4">
          <ConfigIssueNotice issues={activeIssues} />
        </div>
      )}
      {saasAdmin && (
        <div className="shrink-0 px-6 pt-4">
          <p className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
            <span>{t("dashboard:settings_moved_to_console")}</span>
            {ADMIN_CONSOLE_URL && (
              <a className="font-medium text-primary underline-offset-4 hover:underline" href={ADMIN_CONSOLE_URL} target="_blank" rel="noreferrer">
                {t("dashboard:settings_open_console")}
              </a>
            )}
          </p>
        </div>
      )}
      <SectionContent section={activeSection} />
    </PageShell>
  );
}

function SectionContent({ section }: { section: SettingsSection }) {
  switch (section) {
    case "providers":
      return <ProviderSection />;
    case "default-models":
      return <MediaModelSection />;
    case "endpoints":
      return <EndpointsSection />;
    case "asset-library":
      return <AssetLibrarySection />;
    case "arcreel-agent":
      return <AgentConfigTab />;
    case "agent-memory":
      return <AgentMemorySection />;
    case "external-agent":
      return <ExternalAgentSection />;
    case "access-tokens":
      return <AccessTokensSection />;
    case "market":
      return <MarketSection />;
    case "usage":
      return <UsageRecordsSection />;
    case "reconciliation":
      return <ReconciliationSection />;
    case "general":
      return <GeneralSection />;
    case "prompt-templates":
      return <PromptTemplatesSection />;
    case "about":
      return <AboutSection />;
  }
}

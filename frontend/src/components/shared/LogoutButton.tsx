import { LogOut } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuthStore } from "@/stores/auth-store";
import { goToLoginPage } from "./logout-navigation";

/**
 * Sign out of the workbench. Hidden when nobody is signed in (self-hosted with auth off).
 *
 * After clearing the session we load /login as a full page, so every per-user store
 * (role, balance, projects) starts empty for whoever signs in next.
 */
export function LogoutButton({ tooltipSide }: { tooltipSide?: "top" | "bottom" }) {
  const { t } = useTranslation("common");
  const token = useAuthStore((s) => s.token);
  const username = useAuthStore((s) => s.username);
  const logout = useAuthStore((s) => s.logout);
  if (!token) return null;

  const label = username ? `${t("logout")}（${username}）` : t("logout");
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("logout")}
            onClick={() => {
              logout();
              goToLoginPage();
            }}
          />
        }
      >
        <LogOut aria-hidden />
      </TooltipTrigger>
      <TooltipContent side={tooltipSide}>{label}</TooltipContent>
    </Tooltip>
  );
}

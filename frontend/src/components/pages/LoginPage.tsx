import { useEffect, useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { useAutoFocus } from "@/hooks/useAutoFocus";
import { errMsg, voidPromise } from "@/utils/async";
import { useLocation, useSearch } from "wouter";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/stores/auth-store";
import { safeReturnPath } from "@/utils/safe-url";
import { BRAND } from "@/branding";
import type { LoginResponse, ErrorResponse } from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type AuthMode = "login" | "register";

export function LoginPage() {
  const { t, i18n } = useTranslation(["common", "auth"]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [saasMode, setSaasMode] = useState(false);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [, setLocation] = useLocation();
  const search = useSearch();
  const login = useAuthStore((s) => s.login);
  const usernameRef = useAutoFocus<HTMLInputElement>();

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/auth/status", { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) return;
        const payload: unknown = await res.json();
        if (
          typeof payload === "object" &&
          payload !== null &&
          (payload as { deployment_mode?: unknown }).deployment_mode === "saas"
        ) {
          setSaasMode(true);
        }
      })
      .catch(() => {
        /* keep self-hosted login UI */
      });
    return () => controller.abort();
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      let accessToken: string;

      if (authMode === "register") {
        const resp = await fetch("/api/v1/auth/register", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept-Language": i18n.language || "zh",
          },
          body: JSON.stringify({ username, password }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({})) as Partial<ErrorResponse>;
          const detail = data.detail;
          throw new Error(typeof detail === "string" ? detail : t("auth:register_failed"));
        }
        const data = await resp.json() as LoginResponse;
        accessToken = data.access_token;
      } else {
        const body = new URLSearchParams({
          username,
          password,
          grant_type: "password",
        });
        const resp = await fetch("/api/v1/auth/token", {
          method: "POST",
          headers: {
            "Accept-Language": i18n.language || "zh",
          },
          body,
        });

        if (!resp.ok) {
          const data = await resp.json().catch(() => ({})) as Partial<ErrorResponse>;
          const detail = data.detail;
          throw new Error(typeof detail === "string" ? detail : t("auth:login_failed"));
        }

        const data = await resp.json() as LoginResponse;
        accessToken = data.access_token;
      }

      login(accessToken, username);
      const returnTo = safeReturnPath(new URLSearchParams(search).get("from"));
      setLocation(returnTo ?? "/app/projects");
    } catch (err) {
      setError(errMsg(err, authMode === "register" ? t("auth:register_failed") : t("auth:login_failed")));
    } finally {
      setLoading(false);
    }
  };

  const subtitle =
    authMode === "register" ? t("auth:register_subtitle") : t("auth:login_subtitle");
  const submitLabel =
    authMode === "register"
      ? loading
        ? t("auth:registering")
        : t("auth:register")
      : loading
        ? t("auth:logging_in")
        : t("auth:login");

  return (
    <div data-testid="login-page" className="relative flex h-dvh overflow-y-auto bg-background p-4 text-foreground">
      <div className="m-auto flex w-full max-w-sm flex-col gap-6 rounded-xl border bg-card p-8 shadow-overlay">
        <div className="flex flex-col items-center gap-1.5 text-center">
          <h1 className="flex items-center gap-2 font-editorial text-3xl tracking-tight">
            <picture className="dark:hidden">
              <source media="(prefers-reduced-motion: reduce)" srcSet="/logo-light.svg" />
              <img src="/logo-animated-light.svg" alt="" aria-hidden className="block size-7" />
            </picture>
            <picture className="hidden dark:block">
              <source media="(prefers-reduced-motion: reduce)" srcSet="/logo.svg" />
              <img src="/logo-animated.svg" alt="" aria-hidden className="block size-7" />
            </picture>
            <span>{BRAND.name}</span>
          </h1>
          <p className="text-xs font-medium text-muted-foreground">{subtitle}</p>
        </div>

        <form onSubmit={voidPromise(handleSubmit)} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="login-username">{t("auth:username")}</Label>
            <Input
              id="login-username"
              type="text"
              autoComplete="username"
              spellCheck={false}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              ref={usernameRef}
              required
              minLength={authMode === "register" ? 3 : undefined}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="login-password">{t("auth:password")}</Label>
            <Input
              id="login-password"
              type="password"
              autoComplete={authMode === "register" ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={authMode === "register" ? 8 : undefined}
            />
          </div>

          {error && (
            <p role="alert" aria-live="polite" className="text-sm text-destructive">
              {error}
            </p>
          )}

          <Button type="submit" size="lg" disabled={loading}>
            {loading && <Loader2 aria-hidden data-icon="inline-start" className="animate-spin" />}
            {submitLabel}
          </Button>
        </form>

        {saasMode && (
          <button
            type="button"
            className="text-center text-sm text-muted-foreground underline-offset-4 hover:underline"
            onClick={() => {
              setError("");
              setAuthMode((m) => (m === "login" ? "register" : "login"));
            }}
          >
            {authMode === "login" ? t("auth:need_account") : t("auth:have_account")}
          </button>
        )}
      </div>
    </div>
  );
}

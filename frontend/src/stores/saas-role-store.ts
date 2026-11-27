import { useEffect } from "react";
import { create } from "zustand";
import { API } from "@/api";
import { useAuthStore } from "@/stores/auth-store";

/**
 * SaaS: is the signed-in user a platform admin (control-plane ``users.is_admin``)?
 *
 * Instance-wide settings (providers, endpoints, object storage, Agent credentials, access tokens,
 * market, usage, global asset library) answer 403 to ordinary members, so their entries are hidden.
 * Self-hosted: everyone is the owner and nothing is hidden.
 */
interface SaasRoleState {
  /** Token the answer belongs to; a new sign-in loads it again. */
  loadedFor: string | null;
  loading: boolean;
  saas: boolean;
  isAdmin: boolean;
  load: (token: string | null) => Promise<void>;
}

export const useSaasRoleStore = create<SaasRoleState>((set, get) => ({
  loadedFor: null,
  loading: false,
  saas: false,
  isAdmin: true,

  load: async (token) => {
    const key = token ?? "";
    if (get().loading || get().loadedFor === key) return;
    set({ loading: true });
    let saas = false;
    try {
      const status = await fetch("/api/v1/auth/status");
      const payload: unknown = status.ok ? await status.json() : null;
      saas =
        typeof payload === "object" &&
        payload !== null &&
        (payload as { deployment_mode?: unknown }).deployment_mode === "saas";
    } catch {
      saas = false; // unknown mode: behave like upstream and hide nothing
    }
    if (!saas) {
      set({ loadedFor: key, loading: false, saas: false, isAdmin: true });
      return;
    }
    try {
      const me = await API.getMeWallet();
      set({ loadedFor: key, loading: false, saas: true, isAdmin: me.is_admin === true });
    } catch {
      // SaaS but the role is unknown: hide admin-only entries rather than show pages that answer 403.
      set({ loadedFor: key, loading: false, saas: true, isAdmin: false });
    }
  },
}));

/** True when admin-only entries should be hidden (SaaS member). */
export function useIsRestrictedMember(): boolean {
  const token = useAuthStore((s) => s.token);
  const { loadedFor, saas, isAdmin, load } = useSaasRoleStore();
  useEffect(() => {
    if (loadedFor !== (token ?? "")) void load(token);
  }, [token, loadedFor, load]);
  return loadedFor === (token ?? "") && saas && !isAdmin;
}

/** True for a SaaS platform admin (reconciliation and other platform pages). */
export function useIsSaasAdmin(): boolean {
  const token = useAuthStore((s) => s.token);
  const { loadedFor, saas, isAdmin, load } = useSaasRoleStore();
  useEffect(() => {
    if (loadedFor !== (token ?? "")) void load(token);
  }, [token, loadedFor, load]);
  return loadedFor === (token ?? "") && saas && isAdmin;
}

/** True once SaaS mode is confirmed for this sign-in (admins and members alike). */
export function useIsSaas(): boolean {
  const token = useAuthStore((s) => s.token);
  const { loadedFor, saas, load } = useSaasRoleStore();
  useEffect(() => {
    if (loadedFor !== (token ?? "")) void load(token);
  }, [token, loadedFor, load]);
  return loadedFor === (token ?? "") && saas;
}

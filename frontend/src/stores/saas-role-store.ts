import { useEffect } from "react";
import { create } from "zustand";
import { API } from "@/api";
import { ApiRequestError } from "@/api/errors";
import { useAuthStore } from "@/stores/auth-store";

/**
 * SaaS: is the signed-in user a platform admin (control-plane ``users.is_admin``)?
 *
 * Instance-wide settings (providers, endpoints, object storage, Agent credentials, access tokens,
 * market, usage, global asset library) answer 403 to ordinary members, so their entries are hidden.
 * Self-hosted: everyone is the owner and nothing is hidden.
 *
 * Until the answer for the current sign-in is in, admin-only entries stay hidden when this browser
 * last saw a SaaS deployment (no flash of admin menus for members); self-hosted keeps showing
 * everything. A failed role lookup (control plane down, network) hides them too, but is retried
 * with backoff instead of sticking until the next sign-in.
 */
interface SaasRoleState {
  /** Token the answer belongs to; a new sign-in loads it again. */
  loadedFor: string | null;
  loading: boolean;
  saas: boolean;
  isAdmin: boolean;
  load: (token: string | null) => Promise<void>;
}

/** Delays before retrying a failed role lookup; after the last one we wait for the next sign-in. */
const RETRY_DELAYS_MS = [3_000, 10_000, 30_000, 60_000];
let retryFor: string | null = null;
let retryAttempt = 0;
let retryTimer: ReturnType<typeof setTimeout> | null = null;

const SAAS_HINT_KEY = "arcreel:deployment-is-saas";

/** Last deployment mode this browser saw; storage can be missing or throw. */
export function readSaasHint(): boolean {
  try {
    return globalThis.localStorage?.getItem(SAAS_HINT_KEY) === "1";
  } catch {
    return false;
  }
}

function writeSaasHint(saas: boolean): void {
  try {
    if (saas) globalThis.localStorage?.setItem(SAAS_HINT_KEY, "1");
    else globalThis.localStorage?.removeItem(SAAS_HINT_KEY);
  } catch {
    // private mode / disabled storage: the hint is only a convenience
  }
}

function clearRetry(): void {
  if (retryTimer !== null) clearTimeout(retryTimer);
  retryTimer = null;
}

/** 401/403 means "not an admin for this token"; anything else is a transient failure. */
function isDefinitiveDenial(err: unknown): boolean {
  return err instanceof ApiRequestError && (err.status === 401 || err.status === 403);
}

export const useSaasRoleStore = create<SaasRoleState>((set, get) => ({
  loadedFor: null,
  loading: false,
  saas: false,
  isAdmin: false,

  load: async (token) => {
    const key = token ?? "";
    if (get().loading || get().loadedFor === key) return;
    if (retryFor !== key) {
      clearRetry();
      retryFor = key;
      retryAttempt = 0;
    }
    set({ loading: true });
    let saas: boolean;
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
    writeSaasHint(saas);
    if (!saas) {
      set({ loadedFor: key, loading: false, saas: false, isAdmin: true });
      return;
    }
    if (!token) {
      // Signed out (e.g. on /login): asking would answer 401, and the global 401 handler
      // reloads /login, which mounts this hook again — an endless reload loop.
      set({ loadedFor: key, loading: false, saas: true, isAdmin: false });
      return;
    }
    try {
      const me = await API.getMeWallet();
      retryAttempt = 0;
      set({ loadedFor: key, loading: false, saas: true, isAdmin: me.is_admin === true });
    } catch (err) {
      // SaaS but the role is unknown: hide admin-only entries rather than show pages that answer 403.
      set({ loadedFor: key, loading: false, saas: true, isAdmin: false });
      const delay = RETRY_DELAYS_MS[retryAttempt];
      if (!isDefinitiveDenial(err) && delay !== undefined) {
        retryAttempt += 1;
        clearRetry();
        retryTimer = setTimeout(() => {
          retryTimer = null;
          // Clearing loadedFor re-runs the hooks' effects, which call load() again.
          if (get().loadedFor === key) set({ loadedFor: null });
        }, delay);
      }
    }
  },
}));

/** True when admin-only entries should be hidden (SaaS member, or a SaaS role not known yet). */
export function useIsRestrictedMember(): boolean {
  const token = useAuthStore((s) => s.token);
  const { loadedFor, saas, isAdmin, load } = useSaasRoleStore();
  useEffect(() => {
    if (loadedFor !== (token ?? "")) void load(token);
  }, [token, loadedFor, load]);
  if (loadedFor !== (token ?? "")) return readSaasHint();
  return saas && !isAdmin;
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

import { create } from "zustand";
import { API } from "@/api";
import { ApiRequestError } from "@/api/errors";

interface CreditsBalanceState {
  enabled: boolean;
  balance: string | null;
  held: string | null;
  /** CNY view of the wallet (yuan); null when the control plane has no rate. */
  balanceCny: string | null;
  heldCny: string | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  reset: () => void;
}

let refreshSeq = 0;

export const useCreditsBalanceStore = create<CreditsBalanceState>((set) => ({
  enabled: false,
  balance: null,
  held: null,
  balanceCny: null,
  heldCny: null,
  loading: false,
  error: null,

  refresh: async () => {
    const seq = ++refreshSeq;
    set({ loading: true, error: null });
    try {
      const statusRes = await fetch("/api/v1/auth/status");
      if (!statusRes.ok) {
        if (seq === refreshSeq) {
          set({ enabled: false, loading: false, balance: null, held: null, balanceCny: null, heldCny: null });
        }
        return;
      }
      const statusPayload: unknown = await statusRes.json();
      const saas =
        typeof statusPayload === "object" &&
        statusPayload !== null &&
        (statusPayload as { deployment_mode?: unknown }).deployment_mode === "saas";
      if (!saas) {
        if (seq === refreshSeq) {
          set({ enabled: false, loading: false, balance: null, held: null, balanceCny: null, heldCny: null });
        }
        return;
      }
      const me = await API.getMeWallet();
      if (seq !== refreshSeq) return;
      set({
        enabled: true,
        balance: me.wallet.balance,
        held: me.wallet.held,
        balanceCny: me.wallet.balance_cny ?? null,
        heldCny: me.wallet.held_cny ?? null,
        loading: false,
        error: null,
      });
    } catch (err) {
      if (seq !== refreshSeq) return;
      const message = err instanceof Error ? err.message : String(err);
      // 404 = self-hosted or route missing (the message is the server's detail text, not the status)
      if (err instanceof ApiRequestError && err.status === 404) {
        set({
          enabled: false,
          loading: false,
          balance: null,
          held: null,
          balanceCny: null,
          heldCny: null,
          error: null,
        });
        return;
      }
      set({ enabled: true, loading: false, error: message });
    }
  },

  reset: () =>
    set({ enabled: false, balance: null, held: null, balanceCny: null, heldCny: null, loading: false, error: null }),
}));

import { create } from "zustand";
import { API } from "@/api";

interface CreditsBalanceState {
  enabled: boolean;
  balance: string | null;
  held: string | null;
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
  loading: false,
  error: null,

  refresh: async () => {
    const seq = ++refreshSeq;
    set({ loading: true, error: null });
    try {
      const statusRes = await fetch("/api/v1/auth/status");
      if (!statusRes.ok) {
        if (seq === refreshSeq) set({ enabled: false, loading: false, balance: null, held: null });
        return;
      }
      const statusPayload: unknown = await statusRes.json();
      const saas =
        typeof statusPayload === "object" &&
        statusPayload !== null &&
        (statusPayload as { deployment_mode?: unknown }).deployment_mode === "saas";
      if (!saas) {
        if (seq === refreshSeq) set({ enabled: false, loading: false, balance: null, held: null });
        return;
      }
      const me = await API.getMeWallet();
      if (seq !== refreshSeq) return;
      set({
        enabled: true,
        balance: me.wallet.balance,
        held: me.wallet.held,
        loading: false,
        error: null,
      });
    } catch (err) {
      if (seq !== refreshSeq) return;
      const message = err instanceof Error ? err.message : String(err);
      // 404 = self-hosted or route missing
      if (message.includes("404")) {
        set({ enabled: false, loading: false, balance: null, held: null, error: null });
        return;
      }
      set({ enabled: true, loading: false, error: message });
    }
  },

  reset: () => set({ enabled: false, balance: null, held: null, loading: false, error: null }),
}));

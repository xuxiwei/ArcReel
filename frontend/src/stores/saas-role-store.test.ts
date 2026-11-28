import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { API } from "@/api";
import { useSaasRoleStore } from "@/stores/saas-role-store";

function stubStatus(mode: "saas" | "self-hosted") {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ deployment_mode: mode }), { status: 200 }),
  );
}

describe("saas-role-store", () => {
  beforeEach(() => {
    useSaasRoleStore.setState(useSaasRoleStore.getInitialState(), true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not ask for the wallet when signed out (a 401 there reloads /login forever)", async () => {
    stubStatus("saas");
    const wallet = vi.spyOn(API, "getMeWallet");

    await useSaasRoleStore.getState().load(null);

    expect(wallet).not.toHaveBeenCalled();
    expect(useSaasRoleStore.getState()).toMatchObject({ loadedFor: "", saas: true, isAdmin: false });
  });

  it("reads the admin flag from the wallet when signed in", async () => {
    stubStatus("saas");
    vi.spyOn(API, "getMeWallet").mockResolvedValue({
      org_id: "o1",
      username: "admin",
      is_admin: true,
      wallet: { balance: "0", held: "0" },
    });

    await useSaasRoleStore.getState().load("tok");

    expect(useSaasRoleStore.getState()).toMatchObject({ loadedFor: "tok", saas: true, isAdmin: true });
  });

  it("self-hosted: everyone is treated as the owner", async () => {
    stubStatus("self-hosted");
    const wallet = vi.spyOn(API, "getMeWallet");

    await useSaasRoleStore.getState().load("tok");

    expect(wallet).not.toHaveBeenCalled();
    expect(useSaasRoleStore.getState().isAdmin).toBe(true);
  });
});

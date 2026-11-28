import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/stores/auth-store";

const goToLoginPage = vi.hoisted(() => vi.fn());
vi.mock("./logout-navigation", () => ({ goToLoginPage }));

import { LogoutButton } from "./LogoutButton";

describe("LogoutButton", () => {
  beforeEach(() => {
    useAuthStore.setState(useAuthStore.getInitialState(), true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    goToLoginPage.mockClear();
  });

  it("is hidden when nobody is signed in", () => {
    useAuthStore.setState({ token: null, isAuthenticated: false });
    render(<LogoutButton />);
    expect(screen.queryByRole("button", { name: "登出" })).not.toBeInTheDocument();
  });

  it("clears the session and goes to the login page", async () => {
    const user = userEvent.setup();
    const logout = vi.fn();
    useAuthStore.setState({ token: "tok", username: "alice", isAuthenticated: true, logout });

    render(<LogoutButton />);
    await user.click(screen.getByRole("button", { name: "登出" }));

    expect(logout).toHaveBeenCalledTimes(1);
    expect(goToLoginPage).toHaveBeenCalledTimes(1);
  });
});

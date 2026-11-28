import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { FailureObservation } from "@/types";
import { AgentFailureCard } from "./AgentFailureCard";

// A SaaS member: only the conclusion, no settings link and no raw diagnostics.
vi.mock("@/stores/saas-role-store", () => ({
  useIsSaas: () => true,
  useIsRestrictedMember: () => true,
}));

const failure: FailureObservation = {
  version: 1,
  phase: "turn",
  timestamp: "2026-11-28T01:02:03Z",
  project_name: "demo",
  session_id: "session-1",
  summary: {
    key: "authentication",
    source: "sdk_assistant",
    type: "authentication_failed",
    status: 401,
    message: "invalid x-api-key",
  },
  raw: { assistant_message: { error: "authentication_failed" } },
};

describe("AgentFailureCard for a SaaS member", () => {
  it("shows the conclusion without diagnostics or the Agent settings link", () => {
    render(<AgentFailureCard failure={failure} />);

    const card = screen.getByRole("region", { name: "这一轮没有完成" });
    expect(card).not.toHaveTextContent("invalid x-api-key");
    expect(screen.queryByRole("button", { name: "详情" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "复制诊断信息" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Agent 设置" })).not.toBeInTheDocument();
  });
});

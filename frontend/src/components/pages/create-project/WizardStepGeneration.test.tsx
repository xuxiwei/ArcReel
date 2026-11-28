import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { NarrationDeliveryValue } from "@/components/shared/narration-delivery";

import { WizardStepGeneration, type WizardGenerationData } from "./WizardStepGeneration";

const restricted = vi.hoisted(() => ({ value: false }));
vi.mock("@/stores/saas-role-store", () => ({ useIsRestrictedMember: () => restricted.value }));
vi.mock("@/components/shared/ModelConfigSection", () => ({
  ModelConfigSection: () => <div data-testid="model-config" />,
}));

const data: WizardGenerationData = {
  narrationDefaults: null,
  options: { video: [], image: [], text: [], audio: [], providerNames: {}, modelNames: {} },
  providers: [],
  customProviders: [],
  globalDefaults: {
    video: "",
    videoI2V: "",
    videoR2V: "",
    image: "",
    imageT2I: "",
    imageI2I: "",
    textDefault: "",
    textSimple: "",
    textComplex: "",
  },
};

const narration: NarrationDeliveryValue = {
  override: false,
  delivery: "use_tts",
  audioBackend: "",
  narrationVoice: "",
  narrationSpeed: null,
};

function renderStep() {
  render(
    <WizardStepGeneration
      isAd={false}
      usesReferenceImages={false}
      duration={{ targetDuration: 60, episodeTargetDuration: null, speechRate: null }}
      onDurationChange={vi.fn()}
      models={{} as never}
      onModelsChange={vi.fn()}
      narration={narration}
      onNarrationChange={vi.fn()}
      data={data}
      error={null}
    />,
  );
}

describe("WizardStepGeneration", () => {
  beforeEach(() => {
    restricted.value = false;
  });

  it("lets admins pick models and the TTS source", () => {
    renderStep();
    expect(screen.getByTestId("model-config")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "配音设置来源" })).toBeInTheDocument();
  });

  it("SaaS members only choose TTS vs post-production; models follow the platform defaults", () => {
    restricted.value = true;
    renderStep();
    expect(screen.queryByTestId("model-config")).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "配音设置来源" })).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "TTS 配音" })).toBeChecked();
  });
});

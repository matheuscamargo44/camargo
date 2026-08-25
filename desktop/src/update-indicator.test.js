import { describe, expect, it } from "vitest";

import { describeUpdateState } from "./update-indicator.js";

const VERSION = { version: "0.11.0" };

describe("describeUpdateState", () => {
  it("shows the current version while idle, so there is somewhere to go to check", () => {
    /* The first release of this hid the pill entirely while idle. Users
       looking for "where do I update?" found nothing at all. */
    const { label, disabled } = describeUpdateState({ status: "idle" }, VERSION);

    expect(label).toBe("v0.11.0");
    expect(disabled).toBe(false);
  });

  it("confirms the check happened instead of silently doing nothing", () => {
    const { label } = describeUpdateState({ status: "idle" }, { ...VERSION, justChecked: true });

    expect(label).toBe("Up to date");
  });

  it("falls back to a label when the version is unknown, never an empty pill", () => {
    expect(describeUpdateState({ status: "idle" }, {}).label).toBe("Updates");
    expect(describeUpdateState(undefined, VERSION).label).toBe("v0.11.0");
    expect(describeUpdateState(null, {}).label).toBe("Updates");
  });

  it("calls out an available update as an action", () => {
    const { label, variant } = describeUpdateState({ status: "available", version: "0.12.0" }, VERSION);

    expect(label).toBe("Update to 0.12.0");
    expect(variant).toBe("is-action");
  });

  it("shows download progress and blocks a second click mid-download", () => {
    const { label, disabled } = describeUpdateState({ status: "downloading", percent: 37 }, VERSION);

    expect(label).toBe("Downloading 37%");
    expect(disabled).toBe(true);
  });

  it("asks for a restart once the download is ready", () => {
    const { label, variant } = describeUpdateState({ status: "ready", version: "0.12.0" }, VERSION);

    expect(label).toBe("Restart to update");
    expect(variant).toBe("is-ready");
  });

  it("surfaces the failure reason in the tooltip rather than the label", () => {
    const state = { status: "error", message: "net::ERR_INTERNET_DISCONNECTED" };
    const { label, title, variant } = describeUpdateState(state, VERSION);

    expect(label).toBe("Update failed");
    expect(title).toBe("net::ERR_INTERNET_DISCONNECTED");
    expect(variant).toBe("is-error");
  });

  it("never returns an empty label for any state", () => {
    const states = [
      { status: "idle" },
      { status: "checking" },
      { status: "available", version: "1.0.0" },
      { status: "downloading", percent: 0 },
      { status: "ready", version: "1.0.0" },
      { status: "error" },
      { status: "nonsense" },
    ];

    for (const state of states) {
      expect(describeUpdateState(state, VERSION).label, `empty label for ${state.status}`).toBeTruthy();
    }
  });
});

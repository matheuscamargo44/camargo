import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * ./api.js and ./state.js are both mocked so this only tests the
 * controller's own start/stop-fast-polling and badge-building logic, not
 * the real polling/subscriber machinery those modules already have their
 * own tests for.
 */
async function loadControllerWithMocks({ fetchFeatureStatus, isLeagueConnected }) {
  vi.resetModules();
  vi.useFakeTimers();

  let featuresCallback = null;
  vi.doMock("./api.js", () => ({ fetchFeatureStatus }));
  vi.doMock("./state.js", () => ({
    isLeagueConnected,
    onFeaturesUpdate: (cb) => {
      featuresCallback = cb;
      return () => {};
    },
  }));

  const showAramOverlay = vi.fn();
  const hideAramOverlay = vi.fn();
  vi.stubGlobal("window", { camargo: { showAramOverlay, hideAramOverlay } });

  const controller = await import("./aram-overlay-controller.js");
  controller.initAramOverlayController();

  return { emitFeatures: (features) => featuresCallback(features), showAramOverlay, hideAramOverlay };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("initAramOverlayController", () => {
  it("does not start fast polling while the feature is disabled", async () => {
    const fetchFeatureStatus = vi.fn().mockResolvedValue({ recommendation: null });
    const { emitFeatures } = await loadControllerWithMocks({
      fetchFeatureStatus,
      isLeagueConnected: () => true,
    });

    emitFeatures({ aram_augment_advisor: { enabled: false } });
    await vi.advanceTimersByTimeAsync(3000);

    expect(fetchFeatureStatus).not.toHaveBeenCalled();
  });

  it("does not start fast polling while League is disconnected, even if enabled", async () => {
    const fetchFeatureStatus = vi.fn().mockResolvedValue({ recommendation: null });
    const { emitFeatures } = await loadControllerWithMocks({
      fetchFeatureStatus,
      isLeagueConnected: () => false,
    });

    emitFeatures({ aram_augment_advisor: { enabled: true } });
    await vi.advanceTimersByTimeAsync(3000);

    expect(fetchFeatureStatus).not.toHaveBeenCalled();
  });

  it("starts fast polling once enabled+connected, and stops immediately when either flips off", async () => {
    const fetchFeatureStatus = vi.fn().mockResolvedValue({ recommendation: null });
    const { emitFeatures, hideAramOverlay } = await loadControllerWithMocks({
      fetchFeatureStatus,
      isLeagueConnected: () => true,
    });

    emitFeatures({ aram_augment_advisor: { enabled: true } });
    await vi.advanceTimersByTimeAsync(1800); // 3 ticks at 600ms
    expect(fetchFeatureStatus.mock.calls.length).toBeGreaterThanOrEqual(2);

    const callsBeforeStop = fetchFeatureStatus.mock.calls.length;
    emitFeatures({ aram_augment_advisor: { enabled: false } });
    await vi.advanceTimersByTimeAsync(3000);

    expect(fetchFeatureStatus.mock.calls.length).toBe(callsBeforeStop);
    expect(hideAramOverlay).toHaveBeenCalled();
  });

  it("passes badge fraction coordinates through unchanged and flags the OP.GG best slot", async () => {
    const recommendation = {
      active: true,
      trigger: "start",
      champion: "Ahri",
      best_slot: 1,
      regions: [
        { slot: 0, x: 0.1, y: 0.5, w: 0.08, h: 0.12 },
        { slot: 1, x: 0.4, y: 0.5, w: 0.08, h: 0.12 },
        { slot: 2, x: 0.7, y: 0.5, w: 0.08, h: 0.12 },
      ],
      augments: [
        { slot: 0, augment_id: 1, name: "Augment A", icon_url: "http://icon/1", tier: 4, ambiguous: false },
        { slot: 1, augment_id: 2, name: "Augment B", icon_url: "http://icon/2", tier: 3, ambiguous: false },
        // Several augments share this art, so the backend sends no name.
        { slot: 2, augment_id: 3, name: null, icon_url: "http://icon/3", tier: null, ambiguous: true },
      ],
    };
    const fetchFeatureStatus = vi.fn().mockResolvedValue({ recommendation });
    const { emitFeatures, showAramOverlay } = await loadControllerWithMocks({
      fetchFeatureStatus,
      isLeagueConnected: () => true,
    });

    emitFeatures({ aram_augment_advisor: { enabled: true } });
    await vi.advanceTimersByTimeAsync(0);

    expect(showAramOverlay).toHaveBeenCalledWith([
      { slot: 0, x: 0.1, y: 0.5, w: 0.08, h: 0.12, name: "Augment A", iconUrl: "http://icon/1", tier: 4, ambiguous: false, isBest: false },
      { slot: 1, x: 0.4, y: 0.5, w: 0.08, h: 0.12, name: "Augment B", iconUrl: "http://icon/2", tier: 3, ambiguous: false, isBest: true },
      { slot: 2, x: 0.7, y: 0.5, w: 0.08, h: 0.12, name: null, iconUrl: "http://icon/3", tier: null, ambiguous: true, isBest: false },
    ]);
  });

  it("hides the overlay once the recommendation is no longer active (TTL expiry on the backend)", async () => {
    const fetchFeatureStatus = vi
      .fn()
      .mockResolvedValueOnce({ recommendation: { active: true, trigger: "start", champion: "Ahri", best_slot: null, regions: [], augments: [] } })
      .mockResolvedValue({ recommendation: null });
    const { emitFeatures, hideAramOverlay } = await loadControllerWithMocks({
      fetchFeatureStatus,
      isLeagueConnected: () => true,
    });

    emitFeatures({ aram_augment_advisor: { enabled: true } });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(600);

    expect(hideAramOverlay).toHaveBeenCalled();
  });
});

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

  it("passes badge fraction coordinates and justification through unchanged, and flags the best slot", async () => {
    const recommendation = {
      active: true,
      champion: "Ahri",
      best_slot: 1,
      regions: [
        { slot: 0, x: 0.1, y: 0.5, w: 0.08, h: 0.12 },
        { slot: 1, x: 0.4, y: 0.5, w: 0.08, h: 0.12 },
        { slot: 2, x: 0.7, y: 0.5, w: 0.08, h: 0.12 },
      ],
      augments: [
        {
          slot: 0,
          augment_id: 1,
          name: "Augment A",
          icon_url: "http://icon/1",
          tier: 4,
          rank: "A",
          justification: "A solid augment for Ahri.",
          ambiguous: false,
        },
        {
          slot: 1,
          augment_id: 2,
          name: "Augment B",
          icon_url: "http://icon/2",
          tier: 3,
          rank: "S",
          justification: "A top-tier augment for Ahri. (score 82)",
          ambiguous: false,
        },
        // Several augments share this art, so the backend sends no name.
        {
          slot: 2,
          augment_id: 3,
          name: null,
          icon_url: "http://icon/3",
          tier: null,
          rank: null,
          justification: "Several augments share this exact icon, so which one this is can't be told for sure.",
          ambiguous: true,
        },
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
      {
        slot: 0,
        x: 0.1,
        y: 0.5,
        w: 0.08,
        h: 0.12,
        name: "Augment A",
        iconUrl: "http://icon/1",
        tier: 4,
        rank: "A",
        justification: "A solid augment for Ahri.",
        ambiguous: false,
        isBest: false,
      },
      {
        slot: 1,
        x: 0.4,
        y: 0.5,
        w: 0.08,
        h: 0.12,
        name: "Augment B",
        iconUrl: "http://icon/2",
        tier: 3,
        rank: "S",
        justification: "A top-tier augment for Ahri. (score 82)",
        ambiguous: false,
        isBest: true,
      },
      {
        slot: 2,
        x: 0.7,
        y: 0.5,
        w: 0.08,
        h: 0.12,
        name: null,
        iconUrl: "http://icon/3",
        tier: null,
        rank: null,
        justification: "Several augments share this exact icon, so which one this is can't be told for sure.",
        ambiguous: true,
        isBest: false,
      },
    ]);
  });

  it("re-sends when the same champion gets a genuinely different offer", async () => {
    /* The dedup key used to be trigger+champion; a second real offer for
       the same champion (e.g. after a reroll) would have been silently
       skipped as "already shown". */
    const first = {
      active: true,
      champion: "Ahri",
      best_slot: null,
      regions: [{ slot: 0, x: 0.1, y: 0.5, w: 0.08, h: 0.12 }],
      augments: [{ slot: 0, augment_id: 1, name: "A", icon_url: "u", tier: 4, rank: "A", justification: "", ambiguous: false }],
    };
    const second = {
      ...first,
      augments: [{ slot: 0, augment_id: 99, name: "B", icon_url: "u", tier: 3, rank: "S", justification: "", ambiguous: false }],
    };
    const fetchFeatureStatus = vi.fn().mockResolvedValueOnce({ recommendation: first }).mockResolvedValue({ recommendation: second });
    const { emitFeatures, showAramOverlay } = await loadControllerWithMocks({
      fetchFeatureStatus,
      isLeagueConnected: () => true,
    });

    emitFeatures({ aram_augment_advisor: { enabled: true } });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(600);

    expect(showAramOverlay).toHaveBeenCalledTimes(2);
  });

  it("ignores a poll response that resolves after polling already stopped", async () => {
    // The bug: an in-flight request has no way to know polling stopped
    // while it was pending - if it resolved with real badges after the
    // user disabled the feature (or League dropped), it re-showed the
    // overlay with no poller left running to ever hide it again.
    let resolveFirstFetch;
    const fetchFeatureStatus = vi.fn().mockReturnValueOnce(
      new Promise((resolve) => {
        resolveFirstFetch = resolve;
      })
    );
    const { emitFeatures, showAramOverlay, hideAramOverlay } = await loadControllerWithMocks({
      fetchFeatureStatus,
      isLeagueConnected: () => true,
    });

    emitFeatures({ aram_augment_advisor: { enabled: true } }); // sends the in-flight request
    emitFeatures({ aram_augment_advisor: { enabled: false } }); // stops polling before it resolves
    hideAramOverlay.mockClear();

    resolveFirstFetch({
      recommendation: {
        active: true,
        champion: "Ahri",
        best_slot: null,
        regions: [{ slot: 0, x: 0.1, y: 0.5, w: 0.08, h: 0.12 }],
        augments: [{ slot: 0, augment_id: 1, name: "A", icon_url: "u", tier: 4, rank: "A", justification: "", ambiguous: false }],
      },
    });
    await vi.advanceTimersByTimeAsync(0);

    expect(showAramOverlay).not.toHaveBeenCalled();
    expect(hideAramOverlay).not.toHaveBeenCalled(); // stop already hid it; must not fire again either
  });

  it("does not paint an older, out-of-order response over a newer one", async () => {
    // Two overlapping requests can resolve out of order against a backend
    // doing screen capture + an OP.GG lookup. The older one arriving last
    // must not overwrite the newer, already-shown badges.
    let resolveFirstFetch;
    const older = {
      active: true,
      champion: "Ahri",
      best_slot: null,
      regions: [{ slot: 0, x: 0.1, y: 0.5, w: 0.08, h: 0.12 }],
      augments: [{ slot: 0, augment_id: 1, name: "Old", icon_url: "u", tier: 4, rank: "A", justification: "", ambiguous: false }],
    };
    const newer = {
      ...older,
      augments: [{ slot: 0, augment_id: 99, name: "New", icon_url: "u", tier: 3, rank: "S", justification: "", ambiguous: false }],
    };
    const fetchFeatureStatus = vi
      .fn()
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirstFetch = resolve;
        })
      )
      .mockResolvedValueOnce({ recommendation: newer });
    const { emitFeatures, showAramOverlay } = await loadControllerWithMocks({
      fetchFeatureStatus,
      isLeagueConnected: () => true,
    });

    emitFeatures({ aram_augment_advisor: { enabled: true } }); // request 1 (older) sent, left pending
    await vi.advanceTimersByTimeAsync(600); // request 2 (newer) sent and resolves first
    expect(showAramOverlay).toHaveBeenCalledTimes(1);
    showAramOverlay.mockClear();

    resolveFirstFetch({ recommendation: older }); // request 1 finally resolves, after request 2 already landed
    await vi.advanceTimersByTimeAsync(0);

    expect(showAramOverlay).not.toHaveBeenCalled();
  });

  it("hides the overlay once the recommendation is no longer active", async () => {
    const fetchFeatureStatus = vi
      .fn()
      .mockResolvedValueOnce({
        recommendation: { active: true, champion: "Ahri", best_slot: null, regions: [], augments: [] },
      })
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

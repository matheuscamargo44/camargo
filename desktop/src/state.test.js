import { describe, expect, it, vi } from "vitest";

/**
 * state.js is a module-level singleton (subscriber sets, cached
 * features/health/meta), so each test loads a fresh copy with its own
 * mocked ./api.js rather than sharing one import across the file.
 */
async function loadStateWithMockedApi(mocks) {
  vi.resetModules();
  vi.doMock("./api.js", () => mocks);
  return import("./state.js");
}

describe("pollOnce", () => {
  it("keeps data a fulfilled request already got, even when another request in the same poll rejects (Promise.all -> allSettled regression)", async () => {
    const featuresPayload = { instalock: { enabled: true } };
    const fetchFeatures = vi.fn().mockResolvedValue(featuresPayload);
    const fetchHealth = vi.fn().mockRejectedValue(new Error("timeout"));
    const fetchFeatureMeta = vi.fn().mockResolvedValue([{ key: "instalock", category: "Automation" }]);

    const state = await loadStateWithMockedApi({ fetchFeatures, fetchHealth, fetchFeatureMeta });

    await state.refreshNow();

    let latestFeatures;
    state.onFeaturesUpdate((features) => {
      latestFeatures = features;
    });

    // Before the allSettled fix, one rejected request (health) would have
    // thrown inside Promise.all and aborted the whole poll before features
    // was ever assigned, even though the features request had already
    // succeeded.
    expect(latestFeatures).toEqual(featuresPayload);
  });

  it("falls back to an offline health snapshot, rather than showing stale connected state, when health itself fails", async () => {
    const fetchFeatures = vi.fn().mockResolvedValue({});
    const fetchHealth = vi.fn().mockRejectedValue(new Error("timeout"));
    const fetchFeatureMeta = vi.fn().mockResolvedValue([]);

    const state = await loadStateWithMockedApi({ fetchFeatures, fetchHealth, fetchFeatureMeta });

    await state.refreshNow();

    let latestHealth;
    state.onHealthUpdate((health) => {
      latestHealth = health;
    });

    expect(latestHealth).toEqual({ status: "offline", league_connected: false, valorant_connected: false });
  });
});

describe("onFeatureMetaUpdate", () => {
  it("eventually notifies subscribers once meta succeeds after an earlier failure (infinite spinner regression)", async () => {
    const fetchFeatures = vi.fn().mockResolvedValue({});
    const fetchHealth = vi.fn().mockResolvedValue({ status: "ok", league_connected: false, valorant_connected: false });
    const metaPayload = [{ key: "instalock", category: "Automation" }];
    const fetchFeatureMeta = vi.fn().mockRejectedValueOnce(new Error("timeout")).mockResolvedValueOnce(metaPayload);

    const state = await loadStateWithMockedApi({ fetchFeatures, fetchHealth, fetchFeatureMeta });

    let latestMeta = null;
    state.onFeatureMetaUpdate((meta) => {
      latestMeta = meta;
    });

    await state.refreshNow(); // meta fetch fails: a screen built on this poll must not stay showing an empty state without ever hearing about a later success
    expect(latestMeta).toBeNull();

    await state.refreshNow(); // meta fetch succeeds this time
    expect(latestMeta).toEqual(metaPayload);
  });
});

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

let api;
let originalFetch;

beforeAll(async () => {
  vi.stubGlobal("window", { camargo: { backendUrl: "http://127.0.0.1:8731", authToken: "test-token" } });
  api = await import("./api.js");
});

afterEach(() => {
  global.fetch = originalFetch;
  vi.useRealTimers();
});

describe("fetchWithTimeout (via fetchHealth)", () => {
  it("aborts and rejects once the timeout elapses instead of hanging forever", async () => {
    vi.useFakeTimers();
    originalFetch = global.fetch;
    global.fetch = vi.fn(
      (url, options) =>
        new Promise((resolve, reject) => {
          // Mirrors real fetch()'s behavior under an AbortController: never
          // settles on its own, only rejects once the signal aborts.
          options.signal.addEventListener("abort", () => {
            const error = new Error("The operation was aborted");
            error.name = "AbortError";
            reject(error);
          });
        })
    );

    const pending = api.fetchHealth();
    const assertion = expect(pending).rejects.toThrow();
    await vi.advanceTimersByTimeAsync(8000);
    await assertion;
  });

  it("throws when the response is not ok", async () => {
    originalFetch = global.fetch;
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 });

    await expect(api.fetchHealth()).rejects.toThrow(/500/);
  });
});

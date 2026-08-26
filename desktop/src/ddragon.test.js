import { beforeAll, describe, expect, it, vi } from "vitest";

let ddragon;

function mockResponse(payload) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) });
}

beforeAll(async () => {
  // The module prefetches the version, the champion id map, and the skins
  // map at import time - all three must resolve for this to load cleanly.
  vi.stubGlobal(
    "fetch",
    vi.fn((url) => {
      if (url.includes("/api/versions.json")) return mockResponse(["14.24.1"]);
      if (url.includes("/data/en_US/champion.json")) {
        return mockResponse({
          data: {
            MonkeyKing: { id: "MonkeyKing", name: "Wukong" },
            Kaisa: { id: "Kaisa", name: "Kai'Sa" },
            Ahri: { id: "Ahri", name: "Ahri" },
          },
        });
      }
      if (url.includes("/skins.json")) return mockResponse({});
      return mockResponse({});
    })
  );

  ddragon = await import("./ddragon.js");
  // Let the module's own top-level prefetch promises settle before any test
  // runs, so championIdByName is populated the way it would be in the app
  // after a moment of runtime.
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
});

describe("championSquareUrl", () => {
  it("uses the real DataDragon id for a champion whose id differs from its name", () => {
    // The bug: stripping punctuation from the display name guessed "Wukong"
    // instead of the real id "MonkeyKing", 404-ing the icon.
    expect(ddragon.championSquareUrl("Wukong")).toContain("/MonkeyKing.png");
  });

  it("resolves an apostrophe'd name to its real id", () => {
    expect(ddragon.championSquareUrl("Kai'Sa")).toContain("/Kaisa.png");
  });

  it("still works for a champion whose id equals its name", () => {
    expect(ddragon.championSquareUrl("Ahri")).toContain("/Ahri.png");
  });

  it("returns an empty string for a falsy input", () => {
    expect(ddragon.championSquareUrl("")).toBe("");
  });
});

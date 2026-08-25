import { beforeEach, describe, expect, it, vi } from "vitest";

import { createUpdateManager } from "./update-manager.js";

/** Stand-in for electron-updater's autoUpdater: records calls and lets a
 * test fire the events the real one emits. */
function makeStubUpdater() {
  const handlers = {};
  return {
    autoDownload: true,
    autoInstallOnAppQuit: true,
    on(event, handler) {
      handlers[event] = handler;
    },
    emit(event, payload) {
      handlers[event]?.(payload);
    },
    checkForUpdates: vi.fn().mockResolvedValue(undefined),
    downloadUpdate: vi.fn().mockResolvedValue(undefined),
    quitAndInstall: vi.fn(),
    handlers,
  };
}

function makeManager({ isPackaged = true } = {}) {
  const updater = makeStubUpdater();
  const states = [];
  const manager = createUpdateManager({
    updater,
    isPackaged,
    onStateChange: (state) => states.push(state),
  });
  return { manager, updater, states };
}

describe("createUpdateManager", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("never downloads on its own", () => {
    /* A ~110MB surprise download on a metered connection is hostile, so
       the user has to ask for it. */
    const { manager, updater } = makeManager();

    manager.start();

    expect(updater.autoDownload).toBe(false);
    expect(updater.autoInstallOnAppQuit).toBe(false);
  });

  it("stays inert when not packaged, where there is no feed to talk to", async () => {
    const { manager, updater } = makeManager({ isPackaged: false });

    manager.start();
    await vi.advanceTimersByTimeAsync(60_000);
    await manager.check();
    await manager.download();

    expect(updater.checkForUpdates).not.toHaveBeenCalled();
    expect(updater.downloadUpdate).not.toHaveBeenCalled();
    expect(manager.enabled).toBe(false);
  });

  it("walks available -> downloading -> ready as the updater reports progress", async () => {
    const { manager, updater } = makeManager();
    manager.start();

    updater.emit("update-available", { version: "1.2.3" });
    expect(manager.getState()).toMatchObject({ status: "available", version: "1.2.3" });

    await manager.download();
    expect(updater.downloadUpdate).toHaveBeenCalled();

    updater.emit("download-progress", { percent: 42.7 });
    expect(manager.getState()).toMatchObject({ status: "downloading", percent: 43 });

    updater.emit("update-downloaded", { version: "1.2.3" });
    expect(manager.getState()).toMatchObject({ status: "ready", version: "1.2.3", percent: 100 });
  });

  it("reports no update as idle rather than leaving the button stuck on checking", () => {
    const { manager, updater } = makeManager();
    manager.start();

    updater.emit("checking-for-update");
    expect(manager.getState().status).toBe("checking");

    updater.emit("update-not-available", {});
    expect(manager.getState().status).toBe("idle");
  });

  it("surfaces an updater error without throwing", () => {
    const { manager, updater } = makeManager();
    manager.start();

    updater.emit("error", new Error("net::ERR_INTERNET_DISCONNECTED"));

    expect(manager.getState()).toMatchObject({
      status: "error",
      message: "net::ERR_INTERNET_DISCONNECTED",
    });
  });

  it("only downloads from the available state", async () => {
    const { manager, updater } = makeManager();
    manager.start();

    await manager.download(); // still idle

    expect(updater.downloadUpdate).not.toHaveBeenCalled();
  });

  it("only installs once the download finished", () => {
    const { manager, updater } = makeManager();
    manager.start();

    updater.emit("update-available", { version: "1.2.3" });
    expect(manager.install()).toBe(false);
    expect(updater.quitAndInstall).not.toHaveBeenCalled();

    updater.emit("update-downloaded", { version: "1.2.3" });
    expect(manager.install()).toBe(true);
    expect(updater.quitAndInstall).toHaveBeenCalled();
  });

  it("checks shortly after start and then on an interval, and stops cleanly", async () => {
    const { manager, updater } = makeManager();
    manager.start();

    expect(updater.checkForUpdates).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(20_000);
    expect(updater.checkForUpdates).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(6 * 60 * 60 * 1000);
    expect(updater.checkForUpdates).toHaveBeenCalledTimes(2);

    manager.stop();
    await vi.advanceTimersByTimeAsync(12 * 60 * 60 * 1000);
    expect(updater.checkForUpdates).toHaveBeenCalledTimes(2);
  });
});

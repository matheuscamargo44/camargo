import { afterEach, describe, expect, it, vi } from "vitest";
import { EventEmitter } from "events";
import {
  createBackendManager,
  FAILURE_THRESHOLD,
  POST_SPAWN_GRACE_MS,
  MAX_RESTARTS_PER_WINDOW,
  MIN_RESTART_SPACING_MS,
} from "./backend-manager.js";

function fakeChild(pid) {
  const child = new EventEmitter();
  child.pid = pid;
  return child;
}

/** Distinguishes the real backend spawn from the short-lived taskkill
 * helper spawns, the way the real spawn() call would (different command),
 * and hands the test a handle to the "current" backend child so it can
 * simulate a crash by emitting its own "exit".
 */
function createSpawnFn() {
  const state = { backendChild: null, backendPid: 100, calls: [] };
  const spawnFn = vi.fn((cmd, args) => {
    state.calls.push([cmd, args]);
    if (cmd === "taskkill") {
      const child = fakeChild(undefined);
      queueMicrotask(() => child.emit("exit", 0, null));
      return child;
    }
    state.backendPid += 1;
    const child = fakeChild(state.backendPid);
    state.backendChild = child;
    return child;
  });
  return { spawnFn, state };
}

function withPlatform(value, fn) {
  const original = Object.getOwnPropertyDescriptor(process, "platform");
  Object.defineProperty(process, "platform", { value, configurable: true });
  try {
    return fn();
  } finally {
    Object.defineProperty(process, "platform", original);
  }
}

const silentLog = { error: () => {} };

afterEach(() => {
  vi.useRealTimers();
});

describe("killStale", () => {
  it("spawns taskkill by image name on win32 in packaged mode", async () => {
    const { spawnFn } = createSpawnFn();
    const manager = createBackendManager({
      target: { mode: "packaged", exePath: "C:/app/camargo-backend.exe" },
      authToken: "tok",
      backendUrl: "http://127.0.0.1:8731",
      spawnFn,
      log: silentLog,
    });

    await withPlatform("win32", () => manager.killStale());

    expect(spawnFn).toHaveBeenCalledWith("taskkill", ["/IM", "camargo-backend.exe", "/F"], expect.any(Object));
  });

  it("is a no-op in dev mode, even on win32", async () => {
    const { spawnFn } = createSpawnFn();
    const manager = createBackendManager({
      target: { mode: "dev", cwd: "/repo/backend" },
      authToken: "tok",
      backendUrl: "http://127.0.0.1:8731",
      spawnFn,
      log: silentLog,
    });

    await withPlatform("win32", () => manager.killStale());

    expect(spawnFn).not.toHaveBeenCalled();
  });

  it("is a no-op on non-Windows", async () => {
    const { spawnFn } = createSpawnFn();
    const manager = createBackendManager({
      target: { mode: "packaged", exePath: "/app/camargo-backend" },
      authToken: "tok",
      backendUrl: "http://127.0.0.1:8731",
      spawnFn,
      log: silentLog,
    });

    await withPlatform("darwin", () => manager.killStale());

    expect(spawnFn).not.toHaveBeenCalled();
  });
});

describe("crash recovery", () => {
  it("an unexpected exit triggers exactly one respawn", async () => {
    const { spawnFn, state } = createSpawnFn();
    const onRespawn = vi.fn();
    const manager = createBackendManager({
      target: { mode: "dev", cwd: "/repo/backend" },
      authToken: "tok",
      backendUrl: "http://127.0.0.1:8731",
      spawnFn,
      onRespawn,
      log: silentLog,
    });

    manager.start();
    const firstChild = state.backendChild;
    firstChild.emit("exit", 1, null);
    await Promise.resolve();
    await Promise.resolve();

    expect(onRespawn).toHaveBeenCalledTimes(1);
    expect(state.backendChild).not.toBe(firstChild);
  });

  it("does not treat a respawn's own kill as a second crash (the isRestarting race)", async () => {
    vi.useFakeTimers();
    const { spawnFn, state } = createSpawnFn();
    const fetchFn = vi.fn().mockResolvedValue({ ok: false });
    const onRespawn = vi.fn();
    const manager = createBackendManager({
      target: { mode: "dev", cwd: "/repo/backend" },
      authToken: "tok",
      backendUrl: "http://127.0.0.1:8731",
      spawnFn,
      fetchFn,
      onRespawn,
      log: silentLog,
    });

    manager.start();
    const originalChild = state.backendChild;
    manager.startWatchdog(1000);

    await vi.advanceTimersByTimeAsync(POST_SPAWN_GRACE_MS);
    await vi.advanceTimersByTimeAsync(1000 * FAILURE_THRESHOLD);

    expect(onRespawn).toHaveBeenCalledTimes(1);
    expect(state.backendChild).not.toBe(originalChild);

    // The OS delivers the killed (old) process's own exit event late, after
    // the replacement is already spawned and running.
    originalChild.emit("exit", null, "SIGKILL");
    await Promise.resolve();

    expect(onRespawn).toHaveBeenCalledTimes(1);
  });

  it("stops auto-respawning once the restart-storm cap is hit, but keeps the watchdog running", async () => {
    vi.useFakeTimers();
    const { state, spawnFn } = createSpawnFn();
    const onRespawn = vi.fn();
    const manager = createBackendManager({
      target: { mode: "dev", cwd: "/repo/backend" },
      authToken: "tok",
      backendUrl: "http://127.0.0.1:8731",
      spawnFn,
      fetchFn: vi.fn().mockResolvedValue({ ok: true }),
      onRespawn,
      log: silentLog,
    });

    manager.start();

    for (let i = 0; i < MAX_RESTARTS_PER_WINDOW + 2; i++) {
      state.backendChild.emit("exit", 1, null);
      await Promise.resolve();
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(MIN_RESTART_SPACING_MS + 10);
    }

    expect(onRespawn).toHaveBeenCalledTimes(MAX_RESTARTS_PER_WINDOW);
  });
});

describe("watchdog", () => {
  it("respawns after FAILURE_THRESHOLD consecutive failed health checks, not before", async () => {
    vi.useFakeTimers();
    const { spawnFn } = createSpawnFn();
    const fetchFn = vi.fn().mockResolvedValue({ ok: false });
    const onRespawn = vi.fn();
    const manager = createBackendManager({
      target: { mode: "dev", cwd: "/repo/backend" },
      authToken: "tok",
      backendUrl: "http://127.0.0.1:8731",
      spawnFn,
      fetchFn,
      onRespawn,
      log: silentLog,
    });

    manager.start();
    manager.startWatchdog(1000);
    // One tick short of the grace boundary: still inside grace, 0 failures counted.
    await vi.advanceTimersByTimeAsync(POST_SPAWN_GRACE_MS - 1000);

    for (let i = 0; i < FAILURE_THRESHOLD - 1; i++) {
      await vi.advanceTimersByTimeAsync(1000);
    }
    expect(onRespawn).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1000);
    expect(onRespawn).toHaveBeenCalledTimes(1);
  });

  it("a healthy check resets the failure count instead of accumulating across blips", async () => {
    vi.useFakeTimers();
    const { spawnFn } = createSpawnFn();
    const fetchFn = vi.fn();
    for (let i = 0; i < FAILURE_THRESHOLD - 1; i++) fetchFn.mockResolvedValueOnce({ ok: false });
    fetchFn.mockResolvedValueOnce({ ok: true });
    fetchFn.mockResolvedValue({ ok: false });
    const onRespawn = vi.fn();
    const manager = createBackendManager({
      target: { mode: "dev", cwd: "/repo/backend" },
      authToken: "tok",
      backendUrl: "http://127.0.0.1:8731",
      spawnFn,
      fetchFn,
      onRespawn,
      log: silentLog,
    });

    manager.start();
    manager.startWatchdog(1000);
    await vi.advanceTimersByTimeAsync(POST_SPAWN_GRACE_MS);

    // FAILURE_THRESHOLD - 1 failures, then one healthy check resets the count.
    for (let i = 0; i < FAILURE_THRESHOLD; i++) {
      await vi.advanceTimersByTimeAsync(1000);
    }
    expect(onRespawn).not.toHaveBeenCalled();
  });

  it("ignores failures inside the post-spawn grace period", async () => {
    vi.useFakeTimers();
    const { spawnFn } = createSpawnFn();
    const fetchFn = vi.fn().mockResolvedValue({ ok: false });
    const onRespawn = vi.fn();
    const manager = createBackendManager({
      target: { mode: "dev", cwd: "/repo/backend" },
      authToken: "tok",
      backendUrl: "http://127.0.0.1:8731",
      spawnFn,
      fetchFn,
      onRespawn,
      log: silentLog,
    });

    manager.start();
    manager.startWatchdog(1000);

    // Many failed checks, but all still inside the grace period.
    await vi.advanceTimersByTimeAsync(POST_SPAWN_GRACE_MS - 1000);

    expect(onRespawn).not.toHaveBeenCalled();
  });
});

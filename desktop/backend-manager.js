/**
 * Owns the Python backend child process's whole lifecycle: spawning it,
 * sweeping away anything orphaned by an unclean previous exit, and
 * detecting + silently recovering from a crash or hang mid-session.
 *
 * Deliberately has zero `electron` imports — only `child_process` and
 * global `fetch` — so it can be unit tested as plain Node code without
 * mocking Electron. `main.js` resolves Electron-specific values
 * (app.isPackaged, process.resourcesPath) into a plain `target` object and
 * passes it in.
 *
 * Both real production bugs this app has had lived in this exact process-
 * lifecycle layer: an orphaned backend left bound to the port by an
 * unclean exit (fixed by killStale()), and a silent hang/crash mid-session
 * that nothing detected (fixed by the watchdog below).
 */
const { spawn: defaultSpawn } = require("child_process");

const DEFAULT_WATCHDOG_INTERVAL_MS = 12000;
// A backend that accepts the TCP connection but never responds must not be
// allowed to hang this check forever - that would silently defeat the
// watchdog entirely.
const HEALTH_CHECK_TIMEOUT_MS = 5000;
// Long enough to ride out a single blip (AV scan, GC pause); short enough
// to self-heal within under a minute.
const FAILURE_THRESHOLD = 3;
// PyInstaller --onefile re-extracts to a temp dir on every launch, so a
// packaged cold start is measurably slower than dev mode. Don't start
// counting failures until the backend has had a real chance to come up.
const POST_SPAWN_GRACE_MS = 25000;
// Restart-storm guard: a flat sliding-window cap, not exponential backoff.
// Backoff exists to protect a shared resource from many clients piling up;
// here there is exactly one client and one process, so a flat cap is
// simpler, deterministic to test, and self-resets as old attempts age out.
const RESTART_WINDOW_MS = 5 * 60 * 1000;
const MAX_RESTARTS_PER_WINDOW = 5;
// Stops an instant-crash-on-launch loop (e.g. AV quarantining the exe)
// from burning the whole restart budget within milliseconds.
const MIN_RESTART_SPACING_MS = 3000;

/**
 * @param {object} options
 * @param {{mode: "packaged", exePath: string} | {mode: "dev", cwd: string}} options.target
 * @param {string} options.authToken
 * @param {string} options.backendUrl
 * @param {(reason: string) => void} [options.onRespawn] - called after a
 *   respawn's new process has been spawned, so the caller can surface it
 *   somewhere the user can actually see (main.js forwards it to the
 *   backend's own /logs/client endpoint).
 */
function createBackendManager({
  target,
  authToken,
  backendUrl,
  spawnFn = defaultSpawn,
  fetchFn = fetch,
  onRespawn = () => {},
  log = console,
}) {
  let proc = null;
  let watchdogTimer = null;
  let consecutiveFailures = 0;
  let watchdogArmedAt = 0;
  let restartTimestamps = [];
  let isStopping = false;
  let respawnInFlight = false;
  // Pids we killed on purpose (a respawn or a graceful stop), keyed by pid
  // rather than a single shared flag - a shared boolean can't tell "this
  // exit event belongs to the process I just killed" from "this is the
  // *next* process crashing" when the two events land close together.
  const intentionalExits = new Set();

  function spawnProcess() {
    const env = { ...process.env, CAMARGO_AUTH_TOKEN: authToken };
    const child =
      target.mode === "packaged"
        ? spawnFn(target.exePath, [], { stdio: "ignore", windowsHide: true, env })
        : spawnFn("uv", ["run", "python", "main.py"], {
            cwd: target.cwd,
            stdio: "inherit",
            windowsHide: true,
            env,
          });

    proc = child;

    child.on("error", (error) => {
      log.error("Failed to start backend:", error);
    });

    child.on("exit", (code, signal) => {
      if (proc === child) proc = null;
      if (isStopping) {
        intentionalExits.delete(child.pid);
        return;
      }
      if (intentionalExits.delete(child.pid)) return;
      log.error(`Backend (pid ${child.pid}) exited unexpectedly: code=${code} signal=${signal}`);
      respawn(`crash: code=${code} signal=${signal}`);
    });
  }

  function killTree(pid) {
    return new Promise((resolve) => {
      if (!pid) {
        resolve();
        return;
      }
      intentionalExits.add(pid);
      if (process.platform === "win32") {
        const killer = spawnFn("taskkill", ["/pid", String(pid), "/T", "/F"], {
          stdio: "ignore",
          windowsHide: true,
        });
        killer.on("exit", () => resolve());
        killer.on("error", () => resolve());
        return;
      }
      try {
        process.kill(pid);
      } catch {
        // already gone
      }
      resolve();
    });
  }

  /**
   * An unclean previous exit (crash, forced task-kill, an installer
   * replacing the app while the old one was still running in the tray) can
   * leave a camargo-backend.exe orphaned and still bound to the port. The
   * single-instance lock guarantees this is the only camargo process
   * running, so any camargo-backend.exe found here is necessarily stale.
   * Startup-time only, packaged-mode only (dev spawns "uv", never produces
   * this image name).
   */
  function killStale() {
    return new Promise((resolve) => {
      if (target.mode !== "packaged" || process.platform !== "win32") {
        resolve();
        return;
      }
      const killer = spawnFn("taskkill", ["/IM", "camargo-backend.exe", "/F"], {
        stdio: "ignore",
        windowsHide: true,
      });
      killer.on("exit", () => resolve());
      killer.on("error", () => resolve());
    });
  }

  async function respawn(reason) {
    if (respawnInFlight || isStopping) return;

    const now = Date.now();
    restartTimestamps = restartTimestamps.filter((t) => now - t < RESTART_WINDOW_MS);
    if (restartTimestamps.length >= MAX_RESTARTS_PER_WINDOW) {
      log.error(
        `Backend respawn budget exhausted (${MAX_RESTARTS_PER_WINDOW} in ${RESTART_WINDOW_MS}ms), giving up: ${reason}`
      );
      return;
    }
    const last = restartTimestamps[restartTimestamps.length - 1];
    if (last !== undefined && now - last < MIN_RESTART_SPACING_MS) return;

    respawnInFlight = true;
    restartTimestamps.push(now);
    try {
      if (proc) await killTree(proc.pid);
      consecutiveFailures = 0;
      watchdogArmedAt = Date.now() + POST_SPAWN_GRACE_MS;
      spawnProcess();
      onRespawn(reason);
    } finally {
      respawnInFlight = false;
    }
  }

  async function checkHealth() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), HEALTH_CHECK_TIMEOUT_MS);
    try {
      const response = await fetchFn(`${backendUrl}/health`, {
        headers: { "X-Camargo-Token": authToken },
        signal: controller.signal,
      });
      return response.ok;
    } catch {
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  function startWatchdog(intervalMs = DEFAULT_WATCHDOG_INTERVAL_MS) {
    watchdogArmedAt = Date.now() + POST_SPAWN_GRACE_MS;
    watchdogTimer = setInterval(async () => {
      if (Date.now() < watchdogArmedAt) return;
      const healthy = await checkHealth();
      if (healthy) {
        consecutiveFailures = 0;
        return;
      }
      consecutiveFailures += 1;
      if (consecutiveFailures >= FAILURE_THRESHOLD) {
        respawn(`hang: ${consecutiveFailures} consecutive failed health checks`);
      }
    }, intervalMs);
  }

  function stopWatchdog() {
    if (watchdogTimer) clearInterval(watchdogTimer);
    watchdogTimer = null;
  }

  async function stop() {
    isStopping = true;
    stopWatchdog();
    if (proc) await killTree(proc.pid);
  }

  return { start: spawnProcess, stop, killStale, startWatchdog, stopWatchdog };
}

module.exports = {
  createBackendManager,
  DEFAULT_WATCHDOG_INTERVAL_MS,
  HEALTH_CHECK_TIMEOUT_MS,
  FAILURE_THRESHOLD,
  POST_SPAWN_GRACE_MS,
  RESTART_WINDOW_MS,
  MAX_RESTARTS_PER_WINDOW,
  MIN_RESTART_SPACING_MS,
};

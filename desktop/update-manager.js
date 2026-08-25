/**
 * In-app updates, backed by the project's own GitHub Releases (the same
 * ones the release workflow publishes) via electron-updater.
 *
 * Kept out of main.js and free of any `electron` import so it can be unit
 * tested with a stub updater, the same way backend-manager.js is.
 *
 * The state machine is deliberately small, because it drives a single
 * button in the topbar:
 *
 *   idle -> checking -> available -> downloading -> ready
 *                    -> idle (nothing new)
 *   (any) -> error
 *
 * Downloading is never automatic: on a metered connection a ~110MB
 * surprise download is hostile, so it waits for the user to ask.
 */

const CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000; // every 6h while the app runs
const INITIAL_CHECK_DELAY_MS = 15 * 1000; // let the backend finish booting first

function createUpdateManager({ updater, onStateChange, isPackaged, log = () => {} }) {
  let state = { status: "idle", version: null, percent: 0, message: null };
  let checkTimer = null;

  function setState(next) {
    state = { ...state, ...next };
    onStateChange(state);
  }

  function getState() {
    return state;
  }

  // An unpacked dev run has no update feed to talk to; electron-updater
  // throws rather than no-oping, so don't wire any of this up.
  const enabled = Boolean(isPackaged);

  function wire() {
    if (!enabled) return;

    // The user decides when to download and when to restart.
    updater.autoDownload = false;
    updater.autoInstallOnAppQuit = false;

    updater.on("checking-for-update", () => setState({ status: "checking", message: null }));

    updater.on("update-available", (info) => {
      log(`update available: ${info?.version}`);
      setState({ status: "available", version: info?.version ?? null, percent: 0, message: null });
    });

    updater.on("update-not-available", () => setState({ status: "idle", version: null, message: null }));

    updater.on("download-progress", (progress) => {
      setState({ status: "downloading", percent: Math.round(progress?.percent ?? 0) });
    });

    updater.on("update-downloaded", (info) => {
      log(`update downloaded: ${info?.version}`);
      setState({ status: "ready", version: info?.version ?? state.version, percent: 100 });
    });

    updater.on("error", (error) => {
      // Being offline is the common case here and is not worth alarming
      // the user about; surface it in the button's tooltip only.
      log(`update error: ${error?.message ?? error}`);
      setState({ status: "error", message: String(error?.message ?? error) });
    });
  }

  async function check({ silent = true } = {}) {
    if (!enabled) {
      if (!silent) setState({ status: "error", message: "Updates only work in the installed app" });
      return;
    }
    try {
      await updater.checkForUpdates();
    } catch (error) {
      log(`checkForUpdates failed: ${error?.message ?? error}`);
      setState({ status: "error", message: String(error?.message ?? error) });
    }
  }

  async function download() {
    if (!enabled || state.status !== "available") return;
    setState({ status: "downloading", percent: 0 });
    try {
      await updater.downloadUpdate();
    } catch (error) {
      log(`downloadUpdate failed: ${error?.message ?? error}`);
      setState({ status: "error", message: String(error?.message ?? error) });
    }
  }

  function install() {
    if (!enabled || state.status !== "ready") return false;
    // Caller is responsible for shutting the backend down first - see
    // main.js; quitAndInstall does not wait for async quit handlers.
    updater.quitAndInstall();
    return true;
  }

  function start() {
    if (!enabled) return;
    wire();
    setTimeout(() => check(), INITIAL_CHECK_DELAY_MS);
    checkTimer = setInterval(() => check(), CHECK_INTERVAL_MS);
  }

  function stop() {
    if (checkTimer) clearInterval(checkTimer);
    checkTimer = null;
  }

  return { start, stop, check, download, install, getState, enabled };
}

module.exports = { createUpdateManager, CHECK_INTERVAL_MS, INITIAL_CHECK_DELAY_MS };

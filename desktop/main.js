const { app, BrowserWindow, Menu, Tray, nativeImage, ipcMain, shell, clipboard, screen } = require("electron");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const { createBackendManager } = require("./backend-manager");
const { createUpdateManager } = require("./update-manager");

const ICON_PATH = path.join(__dirname, "build", "icon.png");
const BACKEND_URL = "http://127.0.0.1:8731";

// Shared secret for the local backend. Generated per run and handed to the
// Python process through its environment, so a web page cannot call the API
// on 127.0.0.1 even though the port is reachable from any browser. Stable
// for the whole Electron process lifetime, including across any mid-session
// respawn - the renderer only ever reads it once (see preload.js), so a
// respawned backend must keep authenticating with this same value.
const AUTH_TOKEN = crypto.randomBytes(32).toString("base64url");

let mainWindow = null;
let overlayWindow = null;
let tray = null;
let isQuitting = false;

/**
 * A respawn (crash recovery or a hung backend) is otherwise invisible in a
 * packaged app - there's no console to see it in. Forward a one-line note
 * through the same /logs/client channel the renderer already uses for its
 * own errors, so it shows up in the Logs tab and the persistent log file.
 * If the backend itself is unreachable (why we're respawning in the first
 * place, or the restart budget is exhausted), fall back to a small file in
 * Electron's own userData dir so the event still leaves a trace somewhere.
 */
async function reportRespawn(reason) {
  const message = `Backend was restarted automatically: ${reason}`;
  try {
    const response = await fetch(`${BACKEND_URL}/logs/client`, {
      method: "POST",
      headers: { "X-Camargo-Token": AUTH_TOKEN, "Content-Type": "application/json" },
      body: JSON.stringify({ level: "WARNING", message, source: "watchdog" }),
    });
    if (response.ok) return;
  } catch {
    // backend still unreachable - fall through to the local file below
  }
  try {
    const logPath = path.join(app.getPath("userData"), "watchdog.log");
    fs.appendFileSync(logPath, `${new Date().toISOString()} ${message}\n`);
  } catch (error) {
    console.error("Failed to record watchdog event:", error);
  }
}

const backendManager = createBackendManager({
  target: app.isPackaged
    ? { mode: "packaged", exePath: path.join(process.resourcesPath, "backend", "camargo-backend.exe") }
    : { mode: "dev", cwd: path.join(__dirname, "..", "backend") },
  authToken: AUTH_TOKEN,
  backendUrl: BACKEND_URL,
  onRespawn: reportRespawn,
});

// Built lazily in whenReady: requiring electron-updater at module load
// would pull in its GitHub feed machinery even for `npm start` dev runs,
// where it has nothing to talk to.
let updateManager = null;

function broadcastUpdateState(state) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("camargo:update-state", state);
  }
}

function createUpdater() {
  const { autoUpdater } = require("electron-updater");
  return createUpdateManager({
    updater: autoUpdater,
    isPackaged: app.isPackaged,
    onStateChange: broadcastUpdateState,
    log: (message) => console.log(`[updater] ${message}`),
  });
}

function createWindow() {
  const startHidden = process.argv.includes("--hidden") || app.getLoginItemSettings().wasOpenedAsHidden;

  mainWindow = new BrowserWindow({
    width: 680,
    height: 480,
    minWidth: 560,
    minHeight: 400,
    title: "camargo",
    icon: ICON_PATH,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // A URL coming back from the backend must open in the user's browser, never
  // inside a window that shares this app's session.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    try {
      if (/^https?:$/.test(new URL(url).protocol)) shell.openExternal(url);
    } catch {
      // malformed URL: just deny
    }
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (url !== mainWindow.webContents.getURL()) event.preventDefault();
  });

  mainWindow.loadFile(path.join(__dirname, "src", "index.html"));

  if (!startHidden) {
    mainWindow.once("ready-to-show", () => mainWindow.show());
  }

  // Closing the window only hides it to keep background automations running
  mainWindow.on("close", (event) => {
    if (isQuitting) return;
    event.preventDefault();
    mainWindow.hide();
  });
}

// Second, always-on-top, click-through, transparent window for the ARAM
// Augments badges (see aram-overlay-controller.js). Kept hidden with an
// empty render until there is something to show - never steals focus or
// blocks a click meant for the game underneath it.
function createOverlayWindow() {
  const { bounds } = screen.getPrimaryDisplay();

  overlayWindow = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: false,
    hasShadow: false,
    resizable: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "overlay-preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  overlayWindow.setIgnoreMouseEvents(true, { forward: true });
  // "screen-saver" level is what lets this sit above a borderless-fullscreen
  // game window - the default always-on-top level does not.
  overlayWindow.setAlwaysOnTop(true, "screen-saver");
  overlayWindow.loadFile(path.join(__dirname, "src", "overlay.html"));
}

function showWindow() {
  if (!mainWindow) {
    createWindow();
    return;
  }
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

function updateTrayMenu() {
  if (!tray) return;
  const isAutoLaunch = app.getLoginItemSettings().openAtLogin;

  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Open camargo", click: showWindow },
      { type: "separator" },
      {
        label: "Start with Windows",
        type: "checkbox",
        checked: isAutoLaunch,
        click: (item) => {
          app.setLoginItemSettings({
            openAtLogin: item.checked,
            openAsHidden: true,
            path: process.execPath,
            args: ["--hidden"],
          });
          updateTrayMenu();
        },
      },
      { type: "separator" },
      {
        label: "Quit",
        click: () => {
          isQuitting = true;
          app.quit();
        },
      },
    ])
  );
}

function createTray() {
  const icon = nativeImage.createFromPath(ICON_PATH).resize({ width: 16, height: 16 });
  tray = new Tray(icon);
  tray.setToolTip("camargo");
  updateTrayMenu();
  tray.on("click", showWindow);
}

// Synchronous so the preload can expose the token before the first fetch runs
ipcMain.on("camargo:get-auth-token", (event) => {
  event.returnValue = AUTH_TOKEN;
});

ipcMain.on("camargo:get-version", (event) => {
  event.returnValue = app.getVersion();
});

// The Logs tab hands the user a block of text to paste elsewhere.
ipcMain.handle("camargo:copy-text", (_event, text) => {
  clipboard.writeText(String(text ?? ""));
  return true;
});

// The renderer already polls the backend for the current recommendation
// (see aram-overlay-controller.js) - these just relay "here's what to show
// right now" to the overlay window, which never fetches anything itself.
ipcMain.on("camargo:aram-overlay-show", (_event, payload) => {
  if (!overlayWindow) return;
  overlayWindow.webContents.send("camargo:aram-overlay-render", payload);
  if (!overlayWindow.isVisible()) overlayWindow.showInactive();
});

ipcMain.on("camargo:aram-overlay-hide", () => {
  if (overlayWindow) overlayWindow.hide();
});

// -- in-app updates --

ipcMain.handle("camargo:update-get-state", () =>
  updateManager ? updateManager.getState() : { status: "idle", version: null, percent: 0, message: null }
);

ipcMain.handle("camargo:update-check", () => updateManager?.check({ silent: false }));

ipcMain.handle("camargo:update-download", () => updateManager?.download());

ipcMain.handle("camargo:update-install", async () => {
  if (!updateManager) return false;
  // The installer replaces files the backend exe is running from, and
  // quitAndInstall does not wait for async before-quit handlers - so stop
  // the backend explicitly first.
  isQuitting = true;
  await backendManager.stop();
  return updateManager.install();
});

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", showWindow);

  app.whenReady().then(async () => {
    Menu.setApplicationMenu(null);
    await backendManager.killStale();
    backendManager.start();
    backendManager.startWatchdog();
    createWindow();
    createOverlayWindow();
    createTray();

    updateManager = createUpdater();
    updateManager.start();

    app.on("activate", showWindow);
  });

  app.on("window-all-closed", () => {});

  app.on("before-quit", async () => {
    isQuitting = true;
    updateManager?.stop();
    await backendManager.stop();
  });
}


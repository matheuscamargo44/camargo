const { app, BrowserWindow, Menu, Tray, nativeImage, ipcMain, shell } = require("electron");
const path = require("path");
const crypto = require("crypto");
const { spawn } = require("child_process");

const ICON_PATH = path.join(__dirname, "build", "icon.png");

// Shared secret for the local backend. Generated per run and handed to the
// Python process through its environment, so a web page cannot call the API
// on 127.0.0.1 even though the port is reachable from any browser.
const AUTH_TOKEN = crypto.randomBytes(32).toString("base64url");

let backendProcess = null;
let mainWindow = null;
let tray = null;
let isQuitting = false;

function startBackend() {
  const backendEnv = { ...process.env, CAMARGO_AUTH_TOKEN: AUTH_TOKEN };

  if (app.isPackaged) {
    const backendExe = path.join(process.resourcesPath, "backend", "camargo-backend.exe");
    backendProcess = spawn(backendExe, [], { stdio: "ignore", windowsHide: true, env: backendEnv });
  } else {
    const backendDir = path.join(__dirname, "..", "backend");
    backendProcess = spawn("uv", ["run", "python", "main.py"], {
      cwd: backendDir,
      stdio: "inherit",
      windowsHide: true,
      env: backendEnv,
    });
  }

  backendProcess.on("error", (error) => {
    console.error("Failed to start backend:", error);
  });

  backendProcess.on("exit", (code, signal) => {
    const pid = backendProcess ? backendProcess.pid : null;
    backendProcess = null;
    if (!isQuitting) {
      console.error(`Backend (pid ${pid}) exited unexpectedly: code=${code} signal=${signal}`);
    }
  });
}

/**
 * `child.kill()` only signals the direct child. In development that child is
 * `uv`, so the Python process it spawned survives and keeps port 8731 bound,
 * and the next run silently talks to a stale backend.
 */
function stopBackend() {
  if (!backendProcess) return;
  const { pid } = backendProcess;
  backendProcess = null;
  if (!pid) return;

  if (process.platform === "win32") {
    try {
      spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
      return;
    } catch (error) {
      console.error("taskkill failed, falling back to kill():", error);
    }
  }
  try {
    process.kill(pid);
  } catch {
    // already gone
  }
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

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", showWindow);

  app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    startBackend();
    createWindow();
    createTray();

    app.on("activate", showWindow);
  });

  app.on("window-all-closed", () => {});

  app.on("before-quit", () => {
    isQuitting = true;
    stopBackend();
  });
}


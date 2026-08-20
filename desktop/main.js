const { app, BrowserWindow, Menu, Tray, nativeImage, ipcMain } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

const BACKEND_URL = "http://127.0.0.1:8731";
const ICON_PATH = path.join(__dirname, "build", "icon.png");

let backendProcess = null;
let mainWindow = null;
let tray = null;
let isQuitting = false;

function startBackend() {
  if (app.isPackaged) {
    const backendExe = path.join(process.resourcesPath, "backend", "camargo-backend.exe");
    backendProcess = spawn(backendExe, [], { stdio: "ignore", windowsHide: true });
  } else {
    const backendDir = path.join(__dirname, "..", "backend");
    backendProcess = spawn("uv", ["run", "python", "main.py"], {
      cwd: backendDir,
      stdio: "inherit",
      windowsHide: true,
    });
  }

  backendProcess.on("error", (error) => {
    console.error("Failed to start backend:", error);
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

// IPC handlers for auto-launch
ipcMain.handle("get-auto-launch", () => {
  return app.getLoginItemSettings().openAtLogin;
});

ipcMain.handle("set-auto-launch", (_event, enabled) => {
  app.setLoginItemSettings({
    openAtLogin: Boolean(enabled),
    openAsHidden: true,
    path: process.execPath,
    args: ["--hidden"],
  });
  updateTrayMenu();
  return app.getLoginItemSettings().openAtLogin;
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
    if (backendProcess) backendProcess.kill();
  });
}


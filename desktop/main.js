const { app, BrowserWindow, Menu, Tray, nativeImage } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

const BACKEND_URL = "http://127.0.0.1:8731";
const ICON_PATH = path.join(__dirname, "build", "icon.png");

let backendProcess = null;
let mainWindow = null;
let tray = null;
let isQuitting = false;

function startBackend() {
  // windowsHide keeps Windows from popping a console window for the child
  // process; the packaged exe is also built with --noconsole so it never
  // allocates one in the first place (belt and suspenders).
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
  mainWindow.once("ready-to-show", () => mainWindow.show());

  // Closing the window only hides it — the app keeps running in the
  // background (and the backend keeps automations going) until the user
  // quits from the tray menu.
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

function createTray() {
  const icon = nativeImage.createFromPath(ICON_PATH).resize({ width: 16, height: 16 });
  tray = new Tray(icon);
  tray.setToolTip("camargo");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Open camargo", click: showWindow },
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
  tray.on("click", showWindow);
}

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

  // Background execution: closing the window hides it (see the "close"
  // handler above) rather than destroying it, so this normally never fires.
  // Not calling app.quit() here means Electron won't exit even if it does.
  app.on("window-all-closed", () => {});

  app.on("before-quit", () => {
    isQuitting = true;
    if (backendProcess) backendProcess.kill();
  });
}


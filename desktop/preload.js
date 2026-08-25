const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("camargo", {
  backendUrl: "http://127.0.0.1:8731",
  authToken: ipcRenderer.sendSync("camargo:get-auth-token"),
  appVersion: ipcRenderer.sendSync("camargo:get-version"),
  // navigator.clipboard is unavailable on file:// (not a secure context)
  copyText: (text) => ipcRenderer.invoke("camargo:copy-text", text),
  showAramOverlay: (badges) => ipcRenderer.send("camargo:aram-overlay-show", { badges }),
  hideAramOverlay: () => ipcRenderer.send("camargo:aram-overlay-hide"),
});

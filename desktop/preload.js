const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("camargo", {
  backendUrl: "http://127.0.0.1:8731",
  getAutoLaunch: () => ipcRenderer.invoke("get-auto-launch"),
  setAutoLaunch: (enabled) => ipcRenderer.invoke("set-auto-launch", enabled),
});

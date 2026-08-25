const { contextBridge, ipcRenderer } = require("electron");

// Minimal surface for the overlay window: it only ever receives a render
// payload from main, never fetches anything or holds an auth token itself.
contextBridge.exposeInMainWorld("camargoOverlay", {
  onRender: (callback) => ipcRenderer.on("camargo:aram-overlay-render", (_event, payload) => callback(payload)),
});

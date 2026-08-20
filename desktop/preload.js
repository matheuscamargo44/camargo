const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("camargo", {
  backendUrl: "http://127.0.0.1:8731",
});

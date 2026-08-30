const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("practiceLabDesktop", {
  getVersion: () => ipcRenderer.invoke("desktop:get-version"),
  getPlayerSettings: () => ipcRenderer.sendSync("desktop:get-player-settings"),
  savePlayerSettings: settings => ipcRenderer.sendSync("desktop:save-player-settings", settings),
  logPlaybackEvent: event => ipcRenderer.send("desktop:log-playback-event", event),
  getSettings: () => ipcRenderer.invoke("desktop:get-settings"),
  saveSettings: settings => ipcRenderer.invoke("desktop:save-settings", settings),
  prepareCloud: () => ipcRenderer.invoke("desktop:prepare-cloud"),
  exportCloudConnection: () => ipcRenderer.invoke("desktop:export-cloud-connection"),
  chooseCloudConnection: () => ipcRenderer.invoke("desktop:choose-cloud-connection"),
  importCloudConnection: payload => ipcRenderer.invoke("desktop:import-cloud-connection", payload),
  openDataFolder: () => ipcRenderer.invoke("desktop:open-data-folder"),
  clearCache: () => ipcRenderer.invoke("desktop:clear-cache"),
  checkForUpdates: () => ipcRenderer.invoke("desktop:check-for-updates"),
  installUpdate: () => ipcRenderer.invoke("desktop:install-update"),
  onCommand: callback => {
    const listener = (_event, command) => callback(command);
    ipcRenderer.on("desktop:command", listener);
    return () => ipcRenderer.removeListener("desktop:command", listener);
  },
  onUpdateStatus: callback => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("desktop:update-status", listener);
    return () => ipcRenderer.removeListener("desktop:update-status", listener);
  },
});

const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object

// basically instantiates the electronApi object in @./lib/electron.ts
// that way you can call the functions in there from .jsx files and they will invoke node.js functions

// this preload is executed in @main.js before anything else loads.
contextBridge.exposeInMainWorld('electronAPI', {
  findChromePath: () => ipcRenderer.invoke('find-chrome-path'),
  chooseChromePath: () => ipcRenderer.invoke('choose-chrome-path'),
  getSettings: () => ipcRenderer.invoke('get-settings'),
  updateSettings: (settings) => ipcRenderer.invoke('update-settings', settings),
});

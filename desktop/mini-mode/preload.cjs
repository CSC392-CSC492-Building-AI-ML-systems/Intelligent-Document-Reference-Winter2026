const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('miniMode', {
  dismiss: () => ipcRenderer.send('mini-mode:dismiss'),
  focusMainWindow: () => ipcRenderer.send('mini-mode:focus-main-window'),
  openFileInMain: (filePath) =>
    ipcRenderer.send('mini-mode:open-file-in-main', String(filePath || '')),
});

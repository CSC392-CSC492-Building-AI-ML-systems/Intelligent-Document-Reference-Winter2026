const path = require('path');
const { app, BrowserWindow, globalShortcut, ipcMain, screen } = require('electron');

const DEFAULT_HOTKEY = process.env.MINI_MODE_HOTKEY || 'CommandOrControl+Shift+Space';
const MAIN_APP_URL = process.env.MINI_MODE_MAIN_URL || 'http://127.0.0.1:8000/chat';
const MINI_APP_URL = process.env.MINI_MODE_WIDGET_URL || 'http://127.0.0.1:8000/mini';

let mainWindow = null;
let miniWindow = null;
let miniWindowReady = false;

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 980,
    minHeight: 680,
    title: 'Intelligent Document Reference',
    autoHideMenuBar: true,
    backgroundColor: '#0b1220',
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
    },
  });

  mainWindow.loadURL(MAIN_APP_URL);

  mainWindow.on('closed', () => {
    mainWindow = null;
    if (miniWindow) {
      miniWindow.close();
      miniWindow = null;
    }
  });
}

function centerMiniWindow(win) {
  const display = screen.getPrimaryDisplay();
  const { width, height } = display.workAreaSize;
  const [w, h] = win.getSize();
  const x = Math.round((width - w) / 2 + display.workArea.x);
  const y = Math.round(display.workArea.y + Math.max(24, Math.round(height * 0.12)));
  win.setPosition(x, y);
}

function createMiniWindow() {
  miniWindowReady = false;
  miniWindow = new BrowserWindow({
    width: 560,
    height: 360,
    minWidth: 560,
    minHeight: 240,
    maxHeight: 460,
    frame: false,
    transparent: true,
    show: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: true,
    backgroundColor: '#00000000',
    backgroundMaterial: 'none',
    roundedCorners: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      sandbox: true,
    },
  });

  centerMiniWindow(miniWindow);
  miniWindow.setBackgroundColor('#00000000');
  miniWindow.loadURL(MINI_APP_URL);

  miniWindow.webContents.on('did-finish-load', () => {
    miniWindowReady = true;
    if (miniWindow && miniWindow.isVisible()) {
      miniWindow.setBackgroundColor('#00000000');
    }
  });

  miniWindow.on('blur', () => {
    if (miniWindow && miniWindow.isVisible()) {
      miniWindow.hide();
    }
  });

  miniWindow.on('closed', () => {
    miniWindow = null;
    miniWindowReady = false;
  });
}

function toggleMiniMode() {
  if (!miniWindow) {
    createMiniWindow();
    return;
  }

  if (miniWindow.isVisible()) {
    miniWindow.hide();
    return;
  }

  if (!miniWindowReady) {
    miniWindow.webContents.once('did-finish-load', () => {
      if (!miniWindow) {
        return;
      }
      centerMiniWindow(miniWindow);
      miniWindow.show();
      miniWindow.focus();
    });
    return;
  }

  centerMiniWindow(miniWindow);
  miniWindow.show();
  miniWindow.focus();
}

function focusMainWindow() {
  if (!mainWindow) {
    createMainWindow();
    return;
  }

  if (mainWindow.isMinimized()) {
    mainWindow.restore();
  }
  mainWindow.show();
  mainWindow.focus();
}

app.whenReady().then(() => {
  createMainWindow();
  createMiniWindow();

  const ok = globalShortcut.register(DEFAULT_HOTKEY, () => {
    toggleMiniMode();
  });

  if (!ok) {
    console.warn(`Failed to register global hotkey: ${DEFAULT_HOTKEY}`);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
      createMiniWindow();
    }
  });
});

ipcMain.on('mini-mode:dismiss', () => {
  if (miniWindow) {
    miniWindow.hide();
  }
});

ipcMain.on('mini-mode:focus-main-window', () => {
  focusMainWindow();
  if (miniWindow) {
    miniWindow.hide();
  }
});

ipcMain.on('mini-mode:open-file-in-main', (_event, filePath) => {
  focusMainWindow();

  if (mainWindow && filePath) {
    const payload = JSON.stringify(String(filePath));
    const js = `
      try {
        localStorage.setItem('miniMode.openFile', ${payload});
        window.dispatchEvent(new CustomEvent('mini-mode-open-file', { detail: ${payload} }));
        if (location.pathname !== '/chat') {
          location.href = '/chat';
        }
      } catch (_) {}
    `;
    mainWindow.webContents.executeJavaScript(js).catch(() => {});
  }

  if (miniWindow) {
    miniWindow.hide();
  }
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const fsPromises = require('fs').promises;
const os = require('os');
const { execSync } = require('child_process');

const isDev = process.env.NODE_ENV === 'development';
const iconPath = path.join(__dirname, "../../assets/bro_512.png")

let mainWindow;

function createWindow() {

  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    icon: iconPath,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    }
  });

  // Set dock icon on macOS
  if (process.platform === 'darwin') {
    app.dock.setIcon(iconPath);
  }

  const startUrl = isDev 
    ? 'http://localhost:3000' 
    : `file://${path.join(__dirname, '../out/index.html')}`;
  
  mainWindow.loadURL(startUrl);

  if (isDev) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.on('ready', createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

// IPC Handlers

function findChromePath() {
  const system = os.platform().toLowerCase();
  const paths = new Set();
  
  // Check PATH for chrome executables (Unix-like systems only)
  if (system !== 'win32') {
    const chromeNames = ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome'];
    for (const name of chromeNames) {
      try {
        const found = execSync(`which ${name}`, { encoding: 'utf8' }).trim();
        if (found) paths.add(found);
      } catch (e) {
        // Command not found, continue
      }
    }
  }
  
  // Add platform-specific common paths
  if (system === 'darwin') {
    paths.add('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome');
    paths.add('/Applications/Chromium.app/Contents/MacOS/Chromium');
    paths.add(path.join(os.homedir(), 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome'));
  } else if (system === 'win32') {
    paths.add('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe');
    paths.add('C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe');
    paths.add(path.join(os.homedir(), 'AppData\\Local\\Google\\Chrome\\Application\\chrome.exe'));
    paths.add('C:\\Program Files\\Chromium\\Application\\chromium.exe');
  } else {
    // Linux
    paths.add('/usr/bin/google-chrome');
    paths.add('/usr/bin/google-chrome-stable');
    paths.add('/usr/bin/chromium');
    paths.add('/usr/bin/chromium-browser');
    paths.add('/snap/bin/chromium');
  }
  
  // Check which paths actually exist
  const validPaths = [];
  for (const p of paths) {
    try {
      const stats = fs.statSync(p);
      if (stats.isFile()) {
        validPaths.push(p);
      }
    } catch (e) {
      // Path doesn't exist, skip
    }
  }
  
  return validPaths;
}

async function chooseChromePath() {
  const system = os.platform().toLowerCase();
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title: "Select Chrome executable",
    properties: ["openFile"],
    defaultPath:
      system === "darwin"
        ? "/Applications"
        : system === "win32"
        ? "C:\\Program Files\\Google\\Chrome\\Application"
        : "/usr/bin",
    filters:
      system === "darwin"
        ? [{ name: "Chrome", extensions: ["app"] }]
        : [{ name: "Executables", extensions: ["exe", ""] }],
  });

  if (canceled || !filePaths.length) return null;

  // On macOS, user may pick the .app bundle; point to the binary
  const selected = filePaths[0];
  if (system === "darwin" && selected.endsWith(".app")) {
    return path.join(selected, "Contents", "MacOS", "Google Chrome");
  }

  return selected;
}

async function getSettings() {
  const settingsFile = path.join(os.homedir(), '.bro', 'user_settings.json');
  
  try {
    const data = await fsPromises.readFile(settingsFile, 'utf8');
    return JSON.parse(data);
  } catch (e) {
    // File doesn't exist or is invalid, return defaults
    return {
      selected_models: [],
      chrome_path: null,
      initialized: false,
    };
  }
}

async function updateSettings(settings) {
  const settingsDir = path.join(os.homedir(), '.bro');
  const settingsFile = path.join(settingsDir, 'user_settings.json');
  
  // Ensure directory exists
  await fsPromises.mkdir(settingsDir, { recursive: true });
  
  // Write settings file
  await fsPromises.writeFile(settingsFile, JSON.stringify(settings, null, 2), 'utf8');
  
  return settings;
}

async function writeEnvFile(envContent) {
  try {
    const envDir = path.join(os.homedir(), '.bro');
    const envFile = path.join(envDir, '.env');
    
    // Ensure directory exists
    await fsPromises.mkdir(envDir, { recursive: true });
    
    // Write .env file content directly
    await fsPromises.writeFile(envFile, envContent, 'utf8');
    return { success: true };
  } catch (error) {
    console.error('Error in writeEnvFile:', error);
    throw error;
  }
}

async function readEnvFile() {
  const envFile = path.join(os.homedir(), '.bro', '.env');
  
  try {
    const content = await fsPromises.readFile(envFile, 'utf8');
    return content;
  } catch (e) {
    // File doesn't exist, return empty string
    return '';
  }
}

// Register IPC handlers
ipcMain.handle('find-chrome-path', () => {
  return findChromePath();
});

ipcMain.handle('choose-chrome-path', async () => {
  return await chooseChromePath();
});

ipcMain.handle('get-settings', async () => {
  return await getSettings();
});

ipcMain.handle('update-settings', async (_event, settings) => {
  return await updateSettings(settings);
});

ipcMain.handle('write-env-file', async (_event, envContent) => {
  try {
    return await writeEnvFile(envContent);
  } catch (error) {
    console.error('Error writing .env file:', error);
    throw error;
  }
});

ipcMain.handle('read-env-file', async () => {
  return await readEnvFile();
});

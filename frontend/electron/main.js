const { app, BrowserWindow, ipcMain, dialog, protocol, net } = require('electron');
const path = require('path');
const fs = require('fs');
const fsPromises = require('fs').promises;
const os = require('os');
const { execSync, spawn } = require('child_process');
const { pathToFileURL } = require('url');

const isDev = process.env.NODE_ENV === 'development';
const iconPath = path.join(__dirname, "../../assets/bro_512.png")
const BACKEND_URL = 'http://127.0.0.1:8000';
const BACKEND_START_TIMEOUT_MS = 15 * 60 * 1000; // first launch installs Python and every dependency

// Set the application name for macOS
app.setName('Bro');

protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true } },
]);

let mainWindow;
let backendProcess = null;

// Serve the static Next.js export, mapping routes like /dashboard to dashboard.html.
function serveExport() {
  const outDir = path.join(__dirname, '../out');
  protocol.handle('app', (request) => {
    const relative = decodeURIComponent(new URL(request.url).pathname).replace(/^\/+/, '');
    const candidates = relative === '' ? ['index.html'] : [relative, `${relative}.html`];
    const file = candidates
      .map((name) => path.join(outDir, name))
      .find((p) => p.startsWith(outDir + path.sep) && fs.existsSync(p) && fs.statSync(p).isFile());
    return net.fetch(pathToFileURL(file ?? path.join(outDir, '404.html')).toString());
  });
}

async function backendIsUp() {
  try {
    const response = await fetch(`${BACKEND_URL}/`);
    return response.ok;
  } catch (e) {
    return false;
  }
}

// uv writes build files next to the project, so the packaged app runs a copy outside its signed bundle.
function packagedBackendDir() {
  const source = path.join(process.resourcesPath, 'backend');
  const target = path.join(app.getPath('userData'), 'backend');
  const marker = path.join(target, '.version');
  const version = `${app.getVersion()} ${fs.statSync(source).mtimeMs}`;
  if (!fs.existsSync(marker) || fs.readFileSync(marker, 'utf8') !== version) {
    fs.rmSync(target, { recursive: true, force: true });
    fs.cpSync(source, target, { recursive: true });
    fs.writeFileSync(marker, version);
  }
  return target;
}

function startBackend() {
  const dataDir = app.getPath('userData');
  const root = app.isPackaged ? packagedBackendDir() : path.join(__dirname, '../..');
  const uv = app.isPackaged ? path.join(process.resourcesPath, 'bin', 'uv') : 'uv';
  const log = fs.openSync(path.join(dataDir, 'backend.log'), 'w');
  const packagedEnv = app.isPackaged
    ? {
        UV_PROJECT_ENVIRONMENT: path.join(dataDir, 'venv'),
        UV_PYTHON_INSTALL_DIR: path.join(dataDir, 'python'),
        UV_CACHE_DIR: path.join(dataDir, 'uv-cache'),
        UV_PYTHON_PREFERENCE: 'only-managed',
      }
    : {};
  backendProcess = spawn(uv, ['run', '--frozen', '--project', root, 'python', '-m', 'bro.api.main'], {
    cwd: root,
    detached: true,
    stdio: ['ignore', log, log],
    env: {
      ...process.env,
      ...packagedEnv,
      // Apps opened from Finder get a minimal PATH; Splash and other tools live in Homebrew.
      PATH: `/opt/homebrew/bin:/usr/local/bin:${process.env.PATH ?? '/usr/bin:/bin'}`,
    },
  });
  backendProcess.on('exit', () => {
    backendProcess = null;
  });
}

function statusPage(title, detail) {
  const html = `<!doctype html><meta charset="utf-8"><style>
    :root { color-scheme: light dark; font-family: -apple-system, sans-serif; }
    body { display: grid; place-content: center; height: 100vh; margin: 0; text-align: center; }
    p { color: GrayText; max-width: 28rem; }
  </style><h2>${title}</h2><p>${detail}</p>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

async function waitForBackend() {
  if (await backendIsUp()) return true;
  if (!backendProcess) startBackend();
  mainWindow?.loadURL(
    statusPage('Starting Bro…', 'The first launch sets up Bro’s engine, which takes a few minutes and needs internet.'),
  );
  const deadline = Date.now() + BACKEND_START_TIMEOUT_MS;
  while (Date.now() < deadline && backendProcess) {
    if (await backendIsUp()) return true;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  const logPath = path.join(app.getPath('userData'), 'backend.log');
  mainWindow?.loadURL(statusPage('Bro couldn’t start', `Details are in ${logPath}. Quit and reopen Bro to try again.`));
  return false;
}

function stopBackend() {
  if (!backendProcess) return;
  try {
    process.kill(-backendProcess.pid, 'SIGTERM');
  } catch (e) {
    // Already exited
  }
  backendProcess = null;
}

async function createWindow() {

  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    title: 'Bro',
    icon: iconPath,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    }
  });

  // Set dock icon on macOS
  if (process.platform === 'darwin' && fs.existsSync(iconPath)) {
    app.dock.setIcon(iconPath);
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  if (isDev) {
    mainWindow.webContents.openDevTools();
  }

  if (await waitForBackend()) {
    mainWindow?.loadURL(isDev ? 'http://localhost:3000' : 'app://bro/');
  }
}

app.on('ready', () => {
  serveExport();
  void createWindow();
});

app.on('before-quit', stopBackend);

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

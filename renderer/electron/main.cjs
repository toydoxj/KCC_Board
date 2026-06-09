const { app, BrowserWindow, dialog, net, protocol } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");
const { pathToFileURL } = require("node:url");

const API_HOST = "127.0.0.1";
const API_PORT = "8000";

let backendProcess = null;

protocol.registerSchemesAsPrivileged([
  {
    scheme: "kcc-board",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
    },
  },
]);

function getProjectRoot() {
  return app.isPackaged ? process.resourcesPath : path.resolve(__dirname, "..", "..");
}

function getBackendExecutablePath(projectRoot) {
  return path.join(projectRoot, "backend-api", "kcc-board-api.exe");
}

function getPythonPath(projectRoot) {
  const candidates = [
    path.join(projectRoot, ".venv-win", "Scripts", "python.exe"),
    path.join(projectRoot, ".venv", "Scripts", "python.exe"),
    path.join(projectRoot, ".venv", "bin", "python"),
    path.join(projectRoot, ".venv", "bin", "python3"),
  ];

  return candidates.find((candidate) => fs.existsSync(candidate));
}

function getBackendCommand(projectRoot) {
  if (app.isPackaged) {
    const executablePath = getBackendExecutablePath(projectRoot);
    if (!fs.existsSync(executablePath)) {
      return {
        error: `백엔드 실행 파일을 찾을 수 없습니다: ${executablePath}`,
      };
    }
    return {
      command: executablePath,
      args: [],
    };
  }

  const pythonPath = getPythonPath(projectRoot);
  if (!pythonPath) {
    return {
      error: `${path.join(projectRoot, ".venv-win")} 또는 ${path.join(projectRoot, ".venv")} 경로에 Python 가상환경이 필요합니다.`,
    };
  }

  return {
    command: pythonPath,
    args: ["-m", "backend.electron_api"],
  };
}

function getRendererOutDir() {
  return path.resolve(__dirname, "..", "out");
}

function resolveRendererPath(requestUrl) {
  const outDir = getRendererOutDir();
  const url = new URL(requestUrl);
  let pathname = decodeURIComponent(url.pathname);

  if (pathname === "/" || pathname === "") {
    pathname = "/index.html";
  }

  let targetPath = path.normalize(path.join(outDir, pathname));
  if (!targetPath.startsWith(outDir)) {
    targetPath = path.join(outDir, "404.html");
  } else if (!fs.existsSync(targetPath)) {
    const htmlPath = `${targetPath}.html`;
    const indexPath = path.join(targetPath, "index.html");

    if (fs.existsSync(htmlPath)) {
      targetPath = htmlPath;
    } else if (fs.existsSync(indexPath)) {
      targetPath = indexPath;
    } else {
      targetPath = path.join(outDir, "404.html");
    }
  }

  return targetPath;
}

function registerRendererProtocol() {
  protocol.handle("kcc-board", (request) => net.fetch(pathToFileURL(resolveRendererPath(request.url)).toString()));
}

function getBackendLogPath() {
  const logDir = app.isPackaged ? app.getPath("userData") : path.join(getProjectRoot(), "data", "local");
  fs.mkdirSync(logDir, { recursive: true });
  return path.join(logDir, "backend-electron.log");
}

function appendBackendLog(message) {
  const timestamp = new Date().toISOString();
  fs.appendFileSync(getBackendLogPath(), `[${timestamp}] ${message}\n`, "utf8");
}

function startBackend() {
  const projectRoot = getProjectRoot();
  const backendCommand = getBackendCommand(projectRoot);

  if (backendCommand.error) {
    dialog.showErrorBox(
      "백엔드 실행 파일을 찾을 수 없습니다",
      backendCommand.error,
    );
    app.quit();
    return;
  }

  appendBackendLog(`starting backend: ${backendCommand.command} ${backendCommand.args.join(" ")}`);
  backendProcess = spawn(
    backendCommand.command,
    backendCommand.args,
    {
      cwd: projectRoot,
      env: {
        ...process.env,
        PYTHONPATH: projectRoot,
        KCC_BOARD_REPOSITORY: "json",
        KCC_BOARD_SEED_DIR: path.join(projectRoot, "data", "seed"),
        KCC_BOARD_API_HOST: API_HOST,
        KCC_BOARD_API_PORT: API_PORT,
      },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  backendProcess.stdout.on("data", (data) => {
    appendBackendLog(data.toString().trimEnd());
  });
  backendProcess.stderr.on("data", (data) => {
    appendBackendLog(data.toString().trimEnd());
  });
  backendProcess.on("error", (error) => {
    appendBackendLog(`spawn error: ${error.message}`);
  });
  backendProcess.on("exit", (code, signal) => {
    appendBackendLog(`backend exited: code=${code ?? "null"} signal=${signal ?? "null"}`);
    backendProcess = null;
  });
}

async function waitForBackend() {
  const healthUrl = `http://${API_HOST}:${API_PORT}/api/health`;

  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(healthUrl);
      if (response.ok) {
        return;
      }
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }

  throw new Error(`API 서버가 시작되지 않았습니다: ${healthUrl}\n로그 파일: ${getBackendLogPath()}`);
}

async function createWindow() {
  startBackend();

  try {
    await waitForBackend();
  } catch (error) {
    dialog.showErrorBox("API 시작 실패", error instanceof Error ? error.message : String(error));
    app.quit();
    return;
  }

  const mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1180,
    minHeight: 760,
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  if (app.isPackaged) {
    await mainWindow.loadURL("kcc-board://kcc-board/");
  } else {
    await mainWindow.loadURL("http://127.0.0.1:3000");
  }
}

app.whenReady().then(() => {
  registerRendererProtocol();
  return createWindow();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on("before-quit", () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});

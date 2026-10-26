const { app, BrowserWindow, Menu, dialog, ipcMain, net, protocol } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");
const { pathToFileURL } = require("node:url");
const tcp = require("node:net");

const API_HOST = "127.0.0.1";
const API_PORT = "8000";

app.disableHardwareAcceleration();
app.commandLine.appendSwitch("use-gl", "swiftshader");
app.commandLine.appendSwitch("use-angle", "swiftshader");
app.commandLine.appendSwitch("disable-gpu-sandbox");
const isPrimaryInstance = app.requestSingleInstanceLock();
if (!isPrimaryInstance) app.quit();
app.on("second-instance", () => {
  const window = BrowserWindow.getAllWindows()[0];
  if (window) { window.restore(); window.focus(); }
});

let backendProcess = null;
let helpWindow = null;
const pdfJobs = new Set();

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

function safePdfName(value) {
  const fallback = "KCC_구조검토계산서.pdf";
  const name = typeof value === "string" && value.trim() ? value.trim() : fallback;
  const sanitized = name.replace(/[\\/:*?"<>|]/g, "_");
  return sanitized.toLowerCase().endsWith(".pdf") ? sanitized : `${sanitized}.pdf`;
}

function nextQaPdfPath(directory, fileName) {
  const parsed = path.parse(fileName);
  let candidate = path.join(directory, fileName);
  let index = 2;
  while (fs.existsSync(candidate)) {
    candidate = path.join(directory, `${parsed.name}_${index}${parsed.ext}`);
    index += 1;
  }
  return candidate;
}

async function waitForPrintableDocument(webContents) {
  await webContents.executeJavaScript(`(async () => {
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    await Promise.all(Array.from(document.images).map(image => image.decode ? image.decode().catch(() => {}) : Promise.resolve()));
    await Promise.all(Array.from(document.querySelectorAll('svg image')).map(node => new Promise(resolve => {
      const image = new Image();
      image.onload = image.onerror = resolve;
      image.src = node.getAttribute('href') || node.getAttribute('xlink:href') || '';
      if (image.complete) resolve();
    })));
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    return true;
  })()`);
}

function registerPdfHandler() {
  ipcMain.removeHandler("save-report-pdf");
  ipcMain.handle("save-report-pdf", async (event, options = {}) => {
    const webContents = event.sender;
    const jobKey = webContents.id;
    if (pdfJobs.has(jobKey)) {
      return { success: false, canceled: false, error: "PDF 저장이 이미 진행 중입니다." };
    }

    pdfJobs.add(jobKey);
    let temporaryPath = null;
    try {
      const fileName = safePdfName(options.suggestedFileName);
      const qaDirectory = process.env.KCC_STABLE_QA_PDF_DIR;
      let outputPath;
      if (qaDirectory) {
        fs.mkdirSync(qaDirectory, { recursive: true });
        outputPath = nextQaPdfPath(qaDirectory, fileName);
      } else {
        const ownerWindow = BrowserWindow.fromWebContents(webContents);
        const selection = await dialog.showSaveDialog(ownerWindow, {
          title: "구조검토계산서 PDF 저장",
          defaultPath: path.join(app.getPath("documents"), fileName),
          filters: [{ name: "PDF 문서", extensions: ["pdf"] }],
          properties: ["createDirectory", "showOverwriteConfirmation"],
        });
        if (selection.canceled || !selection.filePath) {
          return { success: true, canceled: true };
        }
        outputPath = selection.filePath.toLowerCase().endsWith(".pdf") ? selection.filePath : `${selection.filePath}.pdf`;
      }

      await waitForPrintableDocument(webContents);
      const pdf = await webContents.printToPDF({
        printBackground: true,
        preferCSSPageSize: true,
        pageSize: "A4",
      });
      if (pdf.length < 1000 || pdf.subarray(0, 5).toString("ascii") !== "%PDF-") {
        throw new Error("생성된 PDF 파일이 올바르지 않습니다.");
      }

      temporaryPath = `${outputPath}.${process.pid}.${Date.now()}.tmp`;
      fs.writeFileSync(temporaryPath, pdf);
      fs.copyFileSync(temporaryPath, outputPath);
      fs.unlinkSync(temporaryPath);
      temporaryPath = null;
      return { success: true, canceled: false, path: outputPath };
    } catch (error) {
      appendBackendLog(`PDF save error: ${error instanceof Error ? error.stack || error.message : String(error)}`);
      return {
        success: false,
        canceled: false,
        error: `PDF 저장 실패: ${error instanceof Error ? error.message : String(error)}`,
      };
    } finally {
      if (temporaryPath && fs.existsSync(temporaryPath)) fs.unlinkSync(temporaryPath);
      pdfJobs.delete(jobKey);
    }
  });
}

async function createWindow() {
  try {
    await new Promise((resolve, reject) => {
      const probe = tcp.createServer();
      probe.once("error", () => reject(new Error(`API 포트 ${API_PORT}가 사용 중입니다. 실행 중인 KCC Board를 종료한 뒤 다시 실행하세요.`)));
      probe.listen(Number(API_PORT), API_HOST, () => probe.close(resolve));
    });
    startBackend();
    await waitForBackend();
  } catch (error) {
    dialog.showErrorBox("API 시작 실패", error instanceof Error ? error.message : String(error));
    app.quit();
    return;
  }

  const mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 900,
    minHeight: 760,
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.cjs"),
    },
  });

  mainWindow.once("ready-to-show", () => {
    if (process.env.KCC_REVIEW_QA_HIDDEN !== "1") mainWindow.show();
  });

  if (app.isPackaged) {
    await mainWindow.loadURL("kcc-board://kcc-board/");
  } else {
    await mainWindow.loadURL("http://127.0.0.1:3000");
  }
}

function openHelpWindow() {
  if (helpWindow && !helpWindow.isDestroyed()) { helpWindow.focus(); return; }
  helpWindow = new BrowserWindow({
    width: 1200, height: 900, minWidth: 800, minHeight: 600,
    show: process.env.KCC_REVIEW_QA_HIDDEN !== "1",
    title: "KCC Board 사용 매뉴얼",
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  helpWindow.setMenuBarVisibility(false);
  helpWindow.on("closed", () => { helpWindow = null; });
  const url = app.isPackaged ? "kcc-board://kcc-board/help" : "http://127.0.0.1:3000/help";
  helpWindow.loadURL(url).catch(error => {
    dialog.showErrorBox("사용 매뉴얼을 열 수 없습니다", error instanceof Error ? error.message : String(error));
  });
}

function buildApplicationMenu() {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { role: "fileMenu" }, { role: "editMenu" }, { role: "viewMenu" }, { role: "windowMenu" },
    { role: "help", submenu: [{ label: "사용 매뉴얼", accelerator: "F1", click: openHelpWindow }] },
  ]));
}

if (isPrimaryInstance) app.whenReady().then(() => {
  registerRendererProtocol();
  registerPdfHandler();
  buildApplicationMenu();
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

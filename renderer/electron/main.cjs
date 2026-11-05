const { app, BrowserWindow, Menu, dialog, ipcMain, net, protocol } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { execFile, spawn, spawnSync } = require("node:child_process");
const { pathToFileURL } = require("node:url");
const tcp = require("node:net");
const packageJson = require("../package.json");

// 통일 제목(기술인증 신청명, 2차 심사의견 E-2·B-3). package.json programTitle 단일 기준
const APP_FULL_TITLE = `${packageJson.programTitle} (KCC Board)`;

const API_HOST = "127.0.0.1";
// 백엔드 API 포트는 기동 시 OS가 할당한 빈 포트를 쓴다(2차 심사의견 E-3). 고정 포트 8000 충돌 방지
let apiPort = null;
const BACKEND_IMAGE_NAME = "kcc-board-api.exe";

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
    // createWindow가 받아 "백엔드 시작 실패" 안내로 표시한다(재시도하지 않음)
    const error = new Error(backendCommand.error);
    error.fatal = true;
    throw error;
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
        KCC_BOARD_API_PORT: String(apiPort),
        // 백엔드가 부모 소멸(강제 종료 등)을 감지하여 스스로 종료하도록 PID를 전달한다
        KCC_BOARD_PARENT_PID: String(process.pid),
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
  const healthUrl = `${apiBaseUrl()}/api/health`;

  for (let attempt = 0; attempt < 60; attempt += 1) {
    // 포트 바인드 실패 등으로 백엔드가 먼저 종료되면 기다리지 않고 재시도 단계로 넘긴다
    if (!backendAlive()) {
      const exited = new Error(`백엔드 프로세스가 종료되었습니다(포트 ${apiPort})`);
      exited.backendExited = true;
      throw exited;
    }
    try {
      const response = await fetch(healthUrl);
      if (response.ok) {
        return;
      }
    } catch {
      // 기동 중: 아래에서 대기 후 재확인
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  throw new Error(`API 서버가 응답하지 않습니다(${healthUrl})`);
}

// 빈 포트 확인과 백엔드 바인드 사이에 다른 프로세스가 포트를 선점할 수 있으므로 새 포트로 재시도한다
const BACKEND_START_ATTEMPTS = 3;

async function startBackendWithRetry() {
  let lastError = null;
  for (let attempt = 1; attempt <= BACKEND_START_ATTEMPTS; attempt += 1) {
    if (apiPort === null) apiPort = await findFreePort();
    appendBackendLog(`api port: ${apiPort} (attempt ${attempt})`);
    if (!backendAlive()) startBackend();
    try {
      await waitForBackend();
      return;
    } catch (error) {
      lastError = error;
      if (!(error instanceof Error) || !error.backendExited) throw error;
      appendBackendLog(`backend exited during start, retrying with a new port: ${error.message}`);
      apiPort = null;
    }
  }
  throw lastError;
}

function apiBaseUrl() {
  return `http://${API_HOST}:${apiPort}`;
}

// OS가 할당한 빈 포트를 얻는다(listen(0) 후 즉시 닫음)
function findFreePort() {
  return new Promise((resolve, reject) => {
    const probe = tcp.createServer();
    probe.once("error", reject);
    probe.listen(0, API_HOST, () => {
      const address = probe.address();
      const port = typeof address === "object" && address ? address.port : null;
      probe.close(() => (port ? resolve(port) : reject(new Error("빈 포트를 할당받지 못했습니다."))));
    });
  });
}

function backendStartFailureMessage(cause) {
  return `백엔드 시작 실패: ${cause}. 작업 관리자에서 '${BACKEND_IMAGE_NAME}'를 종료한 뒤 다시 실행하십시오. 문제가 지속되면 로그 파일을 확인하십시오: ${getBackendLogPath()}`;
}

function runWindowsCommand(command, args) {
  return new Promise((resolve) => {
    execFile(command, args, { windowsHide: true }, (error, stdout) => resolve({ error, stdout: String(stdout ?? "") }));
  });
}

// 이전 실행의 백엔드 잔존 프로세스 감지·정리 (Windows 설치본)
async function handleLeftoverBackend() {
  // 이번 실행의 백엔드가 이미 떠 있으면(창 재생성 등) 검사하지 않는다
  if (process.platform !== "win32" || !app.isPackaged || backendAlive()) return;
  const { stdout } = await runWindowsCommand("tasklist", ["/FI", `IMAGENAME eq ${BACKEND_IMAGE_NAME}`, "/NH", "/FO", "CSV"]);
  if (!stdout.toLowerCase().includes(BACKEND_IMAGE_NAME)) return;
  const choice = await dialog.showMessageBox({
    type: "warning",
    title: "잔존 백엔드 프로세스",
    message: `이전 실행의 백엔드 프로세스(${BACKEND_IMAGE_NAME})가 남아 있습니다. 종료 후 다시 시작할까요?`,
    buttons: ["확인", "취소"],
    defaultId: 0,
    cancelId: 1,
    noLink: true,
  });
  if (choice.response !== 0) {
    appendBackendLog("leftover backend kept by user");
    return;
  }
  const { error } = await runWindowsCommand("taskkill", ["/IM", BACKEND_IMAGE_NAME, "/T", "/F"]);
  appendBackendLog(`leftover backend killed: ${error ? error.message : "ok"}`);
}

function backendAlive() {
  return backendProcess !== null && backendProcess.exitCode === null && backendProcess.signalCode === null;
}

// 백엔드 프로세스 트리 종료. Windows는 taskkill /T /F, 그 외는 SIGTERM
function stopBackend(reason) {
  if (!backendAlive()) return;
  const pid = backendProcess.pid;
  appendBackendLog(`stopping backend (${reason}): pid=${pid}`);
  if (process.platform === "win32") {
    const result = spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { windowsHide: true });
    if (result.error || result.status !== 0) {
      appendBackendLog(`taskkill failed: ${result.error ? result.error.message : String(result.stderr ?? "")}`);
    }
  } else {
    backendProcess.kill("SIGTERM");
  }
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

function registerApiBaseUrlHandler() {
  ipcMain.removeHandler("get-api-base-url");
  ipcMain.handle("get-api-base-url", () => {
    if (apiPort === null) throw new Error("백엔드 포트가 아직 할당되지 않았습니다.");
    return apiBaseUrl();
  });
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
    await handleLeftoverBackend();
    await startBackendWithRetry();
  } catch (error) {
    const cause = error instanceof Error ? error.message : String(error);
    appendBackendLog(`backend start failed: ${cause}`);
    stopBackend("start failure");
    dialog.showErrorBox("백엔드 시작 실패", backendStartFailureMessage(cause));
    app.quit();
    return;
  }

  const mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 900,
    minHeight: 760,
    show: false,
    title: APP_FULL_TITLE,
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
    title: `${APP_FULL_TITLE} 사용 매뉴얼`,
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  helpWindow.setMenuBarVisibility(false);
  helpWindow.on("closed", () => { helpWindow = null; });
  const url = app.isPackaged ? "kcc-board://kcc-board/help" : "http://127.0.0.1:3000/help";
  helpWindow.loadURL(url).catch(error => {
    dialog.showErrorBox("사용 매뉴얼을 열 수 없습니다", error instanceof Error ? error.message : String(error));
  });
}

function showAboutDialog() {
  const owner = BrowserWindow.getFocusedWindow() ?? undefined;
  dialog.showMessageBox(owner, {
    type: "info",
    title: "프로그램 정보",
    message: APP_FULL_TITLE,
    detail: `버전 ${packageJson.version}`,
    buttons: ["확인"],
    noLink: true,
  });
}

function buildApplicationMenu() {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { role: "fileMenu" }, { role: "editMenu" }, { role: "viewMenu" }, { role: "windowMenu" },
    { role: "help", submenu: [
      { label: "사용 매뉴얼", accelerator: "F1", click: openHelpWindow },
      { type: "separator" },
      { label: "프로그램 정보", click: showAboutDialog },
    ] },
  ]));
}

if (isPrimaryInstance) app.whenReady().then(() => {
  registerRendererProtocol();
  registerApiBaseUrlHandler();
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
  stopBackend("before-quit");
});

// before-quit 이후에도 백엔드가 살아 있으면 한 번 더 종료한다
app.on("will-quit", () => {
  stopBackend("will-quit");
});

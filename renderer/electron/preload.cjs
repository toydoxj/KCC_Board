const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kccBoard", {
  saveReportPdf: (options) => ipcRenderer.invoke("save-report-pdf", options),
  // 동적 포트 API 주소 (2차 심사의견 E-3)
  getApiBaseUrl: () => ipcRenderer.invoke("get-api-base-url"),
});

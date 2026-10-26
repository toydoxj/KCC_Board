const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kccBoard", {
  saveReportPdf: (options) => ipcRenderer.invoke("save-report-pdf", options),
});

import { contextBridge, ipcRenderer } from "electron";
import { electronAPI } from "@electron-toolkit/preload";
const api = {
  sendQrCode: (qrId) => ipcRenderer.invoke("scan-qr", qrId),
  exportData: () => ipcRenderer.invoke("export-data")
};
if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld("electron", electronAPI);
    contextBridge.exposeInMainWorld("api", api);
  } catch (error) {
    console.error(error);
  }
} else {
  window.electron = electronAPI;
  window.api = api;
}
contextBridge.exposeInMainWorld("electronAPI", {
  // 画面から呼び出す関数を定義
  validateQr: (qrData, eventVal, minSeq, checkEvent, checkSeq) => {
    return ipcRenderer.invoke("validate-qr", { qrData, eventVal, minSeq, checkEvent, checkSeq });
  },
  clearDatabase: () => {
    return ipcRenderer.invoke("clear-database");
  }
});

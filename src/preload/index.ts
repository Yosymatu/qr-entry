import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

// カスタムAPIの定義
const api = {
  sendQrCode: (qrId: string): Promise<any> => ipcRenderer.invoke('scan-qr', qrId),
  exportData: (): Promise<any> => ipcRenderer.invoke('export-data')
}

// Context Isolation の設定に応じて公開方法を変える
if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('api', api)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-ignore (型エラー回避)
  window.electron = electronAPI
  // @ts-ignore (型エラー回避)
  window.api = api
}

contextBridge.exposeInMainWorld('electronAPI', {
    // 画面から呼び出す関数を定義
    validateQr: (qrData: string, eventVal: string, minSeq: number, checkEvent: boolean, checkSeq: boolean) => {
        return ipcRenderer.invoke('validate-qr', { qrData, eventVal, minSeq, checkEvent, checkSeq });
    },
    clearDatabase: () => {
        return ipcRenderer.invoke('clear-database');
    }
});
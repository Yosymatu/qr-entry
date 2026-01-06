import { ElectronAPI } from '@electron-toolkit/preload'


declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      sendQrCode: (qrId: string) => Promise<{
        status: 'success' | 'warning' | 'error';
        message: string;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        user?: any;
      }>
    }
  }
}
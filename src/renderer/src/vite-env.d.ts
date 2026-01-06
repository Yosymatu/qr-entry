/// <reference types="vite/client" />

interface Window {
  api: {
    sendQrCode: (code: string) => Promise<{
      status: 'success' | 'warning' | 'error';
      message: string;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
      user?: any;
    }>
    exportData: () => Promise<{
      status: 'success' | 'cancelled' | 'error';
      message: string;
    }>;
  }
  electronAPI: {
    validateQr: (
      qrData: string,
      eventVal: string,
      minSeq: number,
      checkEvent: boolean,
      checkSeq: boolean
    ) => Promise<{
      status: string;
      msg: string;
    }>;
    clearDatabase: () => Promise<{
      status: string;
      message: string;
    }>;
  }
}
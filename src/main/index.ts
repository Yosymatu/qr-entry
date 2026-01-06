import { app, shell, BrowserWindow, ipcMain, dialog } from 'electron' // dialogを追加
import * as fs from 'fs'; // fsを追加
import { join } from 'path'
import path from 'path';
import { fileURLToPath } from 'url';
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import { initDB, getAsync, runAsync } from './db' // 修正済みのdb.tsからインポート
import Database from 'better-sqlite3'

import { PythonShell, Options } from 'python-shell'

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function createWindow(): void {
  // アイコンのパス
  const iconPath = join(__dirname, '../../public/icon.png')

  // ウィンドウの設定
  const mainWindow = new BrowserWindow({
    width: 900,
    height: 670,
    show: false,
    autoHideMenuBar: true,
    icon: iconPath,
    webPreferences: {
      preload: join(__dirname, '../preload/index.mjs'),
      sandbox: false
    }
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
  })

  // 外部リンクをデフォルトブラウザで開く設定
  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // HMR (Hot Module Replacement) またはファイルのロード
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// アプリの初期化プロセス
app.whenReady().then(() => {
  // Windows用のAppID設定
  electronApp.setAppUserModelId('com.electron')

  // F12キーなどでDevToolsを開く標準ショートカットを有効化
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // ★データベースの初期化
  initDB()

  // ★IPC通信ハンドラー: QRコードスキャン処理
  ipcMain.handle('scan-qr', (_event, qrId: string) => {
    console.log(`QR Code Scanned: ${qrId}`)

    try {
      // 1. 参加者マスタの照会
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const user: any = getAsync('SELECT * FROM participants WHERE id = ?', [qrId])

      if (!user) {
        return { status: 'error', message: '無効なIDです' }
      }

      // 2. 重複チェック (直近のログを確認)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const lastLog: any = getAsync(
        'SELECT * FROM logs WHERE participant_id = ? ORDER BY record_id DESC LIMIT 1',
        [qrId]
      )

      // 退場記録(exit_time)がないまま再入場しようとした場合
      if (lastLog && !lastLog.exit_time) {
        return {
          status: 'warning',
          message: '既に入場済みです',
          user: user
        }
      }

      // 3. 入場記録の保存
      const terminalId = 'PC-01'
      const entryTime = new Date().toISOString()

      runAsync(
        'INSERT INTO logs (participant_id, entry_time, terminal_id) VALUES (?, ?, ?)',
        [qrId, entryTime, terminalId]
      )

      console.log(`Entry Recorded: ${user.id} at ${entryTime}`)

      // 4. 成功レスポンス
      return {
        status: 'success',
        message: '入場しました',
        user: user
      }

    } catch (error) {
      console.error('Database Operation Error:', error)
      return { status: 'error', message: 'システムエラーが発生しました' }
    }
  })

  ipcMain.handle('export-data', async () => {
      try {
        // 1. 保存先ダイアログを表示
        const { canceled, filePath } = await dialog.showSaveDialog({
          title: 'データをエクスポート',
          defaultPath: 'attendance_log.csv',
          filters: [{ name: 'CSV Files', extensions: ['csv'] }]
        });

        if (canceled || !filePath) {
          return { status: 'cancelled', message: '保存がキャンセルされました' };
        }

        // 2. attendance.db からデータ取得（validator.pyと同じDB）
        // 本番環境では app.asar.unpacked フォルダに展開される
        const scriptDir = is.dev
            ? __dirname
            : __dirname.replace('app.asar', 'app.asar.unpacked');
        const dbPath = path.join(scriptDir, 'attendance.db');

        // DBファイルが存在しない場合
        if (!fs.existsSync(dbPath)) {
          return { status: 'error', message: 'データベースが見つかりません' };
        }

        // better-sqlite3を使ってデータ取得
        const db = new Database(dbPath, { readonly: true });
        const logs = db.prepare('SELECT qr_data, entry_time, status, entry_type, ng_reason FROM history ORDER BY entry_time DESC').all() as Array<{ qr_data: string; entry_time: string; status: string; entry_type: string; ng_reason: string }>;
        db.close();

        // 3. CSV文字列を作成
        const header = '"QRデータ","入場日時","ステータス","入場種別","NG理由"\n';

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const rows = logs.map((row: any) => {
          return [
            row.qr_data,
            row.entry_time,
            row.status,
            row.entry_type,
            row.ng_reason
          ].map(val => `"${val || ''}"`).join(',');
        }).join('\n');

        const csvContent = header + rows;

        // 4. ファイル書き込み
        fs.writeFileSync(filePath, '\uFEFF' + csvContent, 'utf8');

        return { status: 'success', message: `エクスポートが完了しました (${logs.length}件)` };

      } catch (error) {
        console.error('Export Error:', error);
        return { status: 'error', message: 'エクスポートに失敗しました: ' + (error as Error).message };
      }
    });

  // データベースクリア
  ipcMain.handle('clear-database', () => {
    try {
      // 本番環境では app.asar.unpacked フォルダに展開される
      const scriptDir = is.dev
          ? __dirname
          : __dirname.replace('app.asar', 'app.asar.unpacked');
      const dbPath = path.join(scriptDir, 'attendance.db');

      if (!fs.existsSync(dbPath)) {
        return { status: 'error', message: 'データベースが見つかりません' };
      }

      const db = new Database(dbPath);
      db.exec('DELETE FROM history');
      db.close();

      return { status: 'success', message: 'データベースをクリアしました' };
    } catch (error) {
      console.error('Clear Database Error:', error);
      return { status: 'error', message: 'クリアに失敗しました: ' + (error as Error).message };
    }
  });

  // ウィンドウ作成
  createWindow()

  // macOSでの再アクティブ化対応
  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

// 全ウィンドウが閉じられたら終了（macOSを除く）
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})


// --- IPC通信: レンダラーからの呼び出しを処理 ---
ipcMain.handle('validate-qr', async (_event, args) => {
    // asarUnpackされたvalidator.pyへのパスを取得
    // 本番環境では app.asar.unpacked フォルダに展開される
    const scriptPath = is.dev
        ? path.join(__dirname, 'validator.py')
        : path.join(__dirname.replace('app.asar', 'app.asar.unpacked'), 'validator.py');

    const options: Options = {
        mode: 'text',
        pythonPath: 'python',
        pythonOptions: ['-u', '-X', 'utf8'],
        encoding: 'utf8',
        args: [
            String(args.qrData),
            String(args.eventVal),
            String(args.minSeq),
            String(args.checkEvent),
            String(args.checkSeq)
        ]
    };

    return new Promise((resolve) => {
        // 第一引数にフルパス(scriptPath)、第二引数にoptionsを渡します
        PythonShell.run(scriptPath, options).then(messages => {
            // messagesはprint出力の配列。最後の出力をJSONパースする
            try {
                if (!messages || messages.length === 0) {
                    resolve({ status: "ERROR", msg: "Pythonからの応答がありません" });
                    return;
                }
                const lastMessage = messages[messages.length - 1];
                const jsonResult = JSON.parse(lastMessage);
                resolve(jsonResult);
            } catch (e) {
                console.error("Parse Error:", e);
                console.log("Raw Message:", messages);
                resolve({ status: "ERROR", msg: "Python出力の解析失敗" });
            }
        }).catch(err => {
            console.error("Python Shell Error:", err);
            resolve({ status: "ERROR", msg: "Python実行エラー: " + err.message });
        });
    });
});
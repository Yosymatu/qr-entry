import { app, ipcMain, dialog, BrowserWindow, shell } from "electron";
import * as fs from "fs";
import path, { join } from "path";
import { fileURLToPath } from "url";
import { electronApp, optimizer, is } from "@electron-toolkit/utils";
import Database from "better-sqlite3";
import { PythonShell } from "python-shell";
import __cjs_mod__ from "node:module";
const __filename = import.meta.filename;
const __dirname = import.meta.dirname;
const require2 = __cjs_mod__.createRequire(import.meta.url);
const dbPath = path.join(app.getPath("userData"), "database.sqlite");
let db;
const initDB = () => {
  try {
    db = new Database(dbPath);
    console.log("DB接続成功:", dbPath);
    createTables();
  } catch (err) {
    console.error("DB接続エラー:", err);
  }
};
const createTables = () => {
  db.exec(`CREATE TABLE IF NOT EXISTS participants (
    id TEXT PRIMARY KEY,
    status TEXT DEFAULT '未登録'
  )`);
  db.exec(`CREATE TABLE IF NOT EXISTS logs (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id TEXT,
    entry_time TEXT,
    exit_time TEXT,
    terminal_id TEXT,
    FOREIGN KEY(participant_id) REFERENCES participants(id)
  )`);
  const stmt = db.prepare(`INSERT OR IGNORE INTO participants (id, status) VALUES (?, ?)`);
  stmt.run("TEST001", "登録済");
};
const getAsync = (sql, params = []) => {
  const stmt = db.prepare(sql);
  return stmt.get(...params);
};
const runAsync = (sql, params = []) => {
  const stmt = db.prepare(sql);
  stmt.run(...params);
};
const __filename$1 = fileURLToPath(import.meta.url);
const __dirname$1 = path.dirname(__filename$1);
function createWindow() {
  const iconPath = join(__dirname$1, "../../public/icon.png");
  const mainWindow = new BrowserWindow({
    width: 900,
    height: 670,
    show: false,
    autoHideMenuBar: true,
    icon: iconPath,
    webPreferences: {
      preload: join(__dirname$1, "../preload/index.mjs"),
      sandbox: false
    }
  });
  mainWindow.on("ready-to-show", () => {
    mainWindow.show();
  });
  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url);
    return { action: "deny" };
  });
  if (is.dev && process.env["ELECTRON_RENDERER_URL"]) {
    mainWindow.loadURL(process.env["ELECTRON_RENDERER_URL"]);
  } else {
    mainWindow.loadFile(join(__dirname$1, "../renderer/index.html"));
  }
}
app.whenReady().then(() => {
  electronApp.setAppUserModelId("com.electron");
  app.on("browser-window-created", (_, window) => {
    optimizer.watchWindowShortcuts(window);
  });
  initDB();
  ipcMain.handle("scan-qr", (_event, qrId) => {
    console.log(`QR Code Scanned: ${qrId}`);
    try {
      const user = getAsync("SELECT * FROM participants WHERE id = ?", [qrId]);
      if (!user) {
        return { status: "error", message: "無効なIDです" };
      }
      const lastLog = getAsync(
        "SELECT * FROM logs WHERE participant_id = ? ORDER BY record_id DESC LIMIT 1",
        [qrId]
      );
      if (lastLog && !lastLog.exit_time) {
        return {
          status: "warning",
          message: "既に入場済みです",
          user
        };
      }
      const terminalId = "PC-01";
      const entryTime = (/* @__PURE__ */ new Date()).toISOString();
      runAsync(
        "INSERT INTO logs (participant_id, entry_time, terminal_id) VALUES (?, ?, ?)",
        [qrId, entryTime, terminalId]
      );
      console.log(`Entry Recorded: ${user.id} at ${entryTime}`);
      return {
        status: "success",
        message: "入場しました",
        user
      };
    } catch (error) {
      console.error("Database Operation Error:", error);
      return { status: "error", message: "システムエラーが発生しました" };
    }
  });
  ipcMain.handle("export-data", async () => {
    try {
      const { canceled, filePath } = await dialog.showSaveDialog({
        title: "データをエクスポート",
        defaultPath: "attendance_log.csv",
        filters: [{ name: "CSV Files", extensions: ["csv"] }]
      });
      if (canceled || !filePath) {
        return { status: "cancelled", message: "保存がキャンセルされました" };
      }
      const scriptDir = is.dev ? __dirname$1 : __dirname$1.replace("app.asar", "app.asar.unpacked");
      const dbPath2 = path.join(scriptDir, "attendance.db");
      if (!fs.existsSync(dbPath2)) {
        return { status: "error", message: "データベースが見つかりません" };
      }
      const db2 = new Database(dbPath2, { readonly: true });
      const logs = db2.prepare("SELECT qr_data, entry_time, status, entry_type, ng_reason FROM history ORDER BY entry_time DESC").all();
      db2.close();
      const header = '"QRデータ","入場日時","ステータス","入場種別","NG理由"\n';
      const rows = logs.map((row) => {
        return [
          row.qr_data,
          row.entry_time,
          row.status,
          row.entry_type,
          row.ng_reason
        ].map((val) => `"${val || ""}"`).join(",");
      }).join("\n");
      const csvContent = header + rows;
      fs.writeFileSync(filePath, "\uFEFF" + csvContent, "utf8");
      return { status: "success", message: `エクスポートが完了しました (${logs.length}件)` };
    } catch (error) {
      console.error("Export Error:", error);
      return { status: "error", message: "エクスポートに失敗しました: " + error.message };
    }
  });
  ipcMain.handle("clear-database", () => {
    try {
      const scriptDir = is.dev ? __dirname$1 : __dirname$1.replace("app.asar", "app.asar.unpacked");
      const dbPath2 = path.join(scriptDir, "attendance.db");
      if (!fs.existsSync(dbPath2)) {
        return { status: "error", message: "データベースが見つかりません" };
      }
      const db2 = new Database(dbPath2);
      db2.exec("DELETE FROM history");
      db2.close();
      return { status: "success", message: "データベースをクリアしました" };
    } catch (error) {
      console.error("Clear Database Error:", error);
      return { status: "error", message: "クリアに失敗しました: " + error.message };
    }
  });
  createWindow();
  app.on("activate", function() {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
ipcMain.handle("validate-qr", async (_event, args) => {
  const scriptPath = is.dev ? path.join(__dirname$1, "validator.py") : path.join(__dirname$1.replace("app.asar", "app.asar.unpacked"), "validator.py");
  const options = {
    mode: "text",
    pythonPath: "python",
    pythonOptions: ["-u", "-X", "utf8"],
    encoding: "utf8",
    args: [
      String(args.qrData),
      String(args.eventVal),
      String(args.minSeq),
      String(args.checkEvent),
      String(args.checkSeq)
    ]
  };
  return new Promise((resolve) => {
    PythonShell.run(scriptPath, options).then((messages) => {
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
    }).catch((err) => {
      console.error("Python Shell Error:", err);
      resolve({ status: "ERROR", msg: "Python実行エラー: " + err.message });
    });
  });
});

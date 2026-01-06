import Database from 'better-sqlite3';
import { app } from 'electron';
import path from 'path';

// 開発環境と本番環境でパスを切り替える場合への備え
const dbPath = path.join(app.getPath('userData'), 'database.sqlite');

let db: Database.Database;

type QueryParam = string | number | null | undefined;

// 初期化関数
export const initDB = () => {
  try {
    db = new Database(dbPath);
    console.log('DB接続成功:', dbPath);
    createTables();
  } catch (err) {
    console.error('DB接続エラー:', err);
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

  // テストデータ投入（開発用）
  const stmt = db.prepare(`INSERT OR IGNORE INTO participants (id, status) VALUES (?, ?)`);
  stmt.run('TEST001', '登録済');
};

// ヘルパー関数: 読み取り(SELECT) - 1行取得
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const getAsync = (sql: string, params: QueryParam[] = []): any => {
  const stmt = db.prepare(sql);
  return stmt.get(...params);
};

// ヘルパー関数: 書き込み(INSERT/UPDATE)
export const runAsync = (sql: string, params: QueryParam[] = []): void => {
  const stmt = db.prepare(sql);
  stmt.run(...params);
};

// ★追加: 複数行取得用のヘルパー関数
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const allAsync = (sql: string, params: QueryParam[] = []): any[] => {
  const stmt = db.prepare(sql);
  return stmt.all(...params);
};

// ★追加: 全ログデータの取得（CSV用）
// 参加者テーブルと結合して、より詳細なデータを取得します
export const getAllLogs = () => {
  const sql = `
    SELECT
      logs.record_id,
      logs.participant_id,
      participants.status,
      logs.entry_time,
      logs.exit_time,
      logs.terminal_id
    FROM logs
    LEFT JOIN participants ON logs.participant_id = participants.id
    ORDER BY logs.record_id DESC
  `;
  return allAsync(sql);
};

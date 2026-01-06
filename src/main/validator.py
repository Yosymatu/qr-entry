import sys
import sqlite3
import datetime
import json  # 追加: JSON出力用
import os

# スクリプトのディレクトリを基準にDBパスを設定
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'attendance.db')

# データベースの初期化（テーブルがなければ作成）
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 全ての読み取りログを記録（PRIMARY KEYをIDに変更）
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  qr_data TEXT,
                  entry_time TEXT,
                  status TEXT,
                  entry_type TEXT,
                  ng_reason TEXT)''')
    conn.commit()
    conn.close()

def log_result(qr_data, status, entry_type, ng_reason=""):
    """結果をDBに記録する共通関数 - 毎回新しいレコードを追加"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    current_time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 常にINSERT（全てのログを記録）
    c.execute("""INSERT INTO history (qr_data, entry_time, status, entry_type, ng_reason)
                VALUES (?, ?, ?, ?, ?)""",
              (qr_data, current_time_str, status, entry_type, ng_reason))

    conn.commit()
    conn.close()

def validate_qr(qr_data, target_event_name, input_min_seq, check_event, check_seq):
    # --- 1. フォーマット解析 ---
    # 想定フォーマット: "イベント名,連番"
    try:
        if "," not in qr_data:
            msg = "フォーマット不正 (カンマなし)"
            log_result(qr_data, "NG", "フォーマットNG", msg)
            return {"status": "NG", "msg": msg}

        qr_event, qr_seq_str = qr_data.split(',', 1)
        qr_seq = int(qr_seq_str)
    except ValueError:
        msg = "フォーマット不正 (数値読み取り不可)"
        log_result(qr_data, "NG", "フォーマットNG", msg)
        return {"status": "NG", "msg": msg}

    # --- 2. イベント名判定（チェックが有効な場合のみ） ---
    if check_event:
        if qr_event != target_event_name:
            msg = f"イベント不一致 (QR: {qr_event})"
            log_result(qr_data, "NG", "イベント不一致", msg)
            return {"status": "NG", "msg": msg}

    # --- 3. 連番判定ロジック（チェックが有効な場合のみ） ---
    # 要件: QRコードの連番が 入力された連番(下限) 未満 の場合にNG
    # 例: 入力=10, QR=9 -> 9 < 10 (True) -> NG (下限より小さい連番)
    if check_seq:
        try:
            min_seq = int(input_min_seq)
            if qr_seq < min_seq:
                msg = f"無効な連番 (下限: {min_seq} > QR: {qr_seq})"
                log_result(qr_data, "NG", "連番NG", msg)
                return {"status": "NG", "msg": msg}
        except ValueError:
            msg = "設定された連番が数値ではありません"
            log_result(qr_data, "NG", "設定エラー", msg)
            return {"status": "NG", "msg": msg}

    # --- 4. データベース照合（再入場ロジック） ---
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 最新の入場記録を取得（OKステータスのもの）
    c.execute("""SELECT entry_time FROM history
                 WHERE qr_data = ? AND status = 'OK'
                 ORDER BY entry_time DESC LIMIT 1""", (qr_data,))
    result = c.fetchone()
    conn.close()

    today_str = datetime.datetime.now().strftime('%Y-%m-%d')

    if result:
        # 過去に入場記録あり
        last_entry_str = result[0]
        last_entry_date = last_entry_str.split(' ')[0]  # YYYY-MM-DD部分のみ抽出

        if last_entry_date == today_str:
            # 同日のため再入場OK
            log_result(qr_data, "OK", "再入場", "")
            return {"status": "OK", "msg": f"再入場 ({qr_seq})"}
        else:
            # 別日のため使用済みNG
            msg = "使用済みチケット (別日に入場歴あり)"
            log_result(qr_data, "NG", "別日使用済", msg)
            return {"status": "NG", "msg": msg}
    else:
        # 初回入場
        log_result(qr_data, "OK", "初回入場", "")
        return {"status": "OK", "msg": f"初回入場 ({qr_seq})"}

# 実行ブロック
if __name__ == '__main__':
    # データベース初期化
    init_db()

    # 結果格納用変数
    result = {}

    if len(sys.argv) < 6:
        result = {"status": "ERROR", "msg": "引数が不足しています"}
    else:
        # Node.jsからの引数を受け取る
        # python-shell経由の場合、sys.argv[1]から順に格納される
        qr_input = sys.argv[1]
        target_event = sys.argv[2]
        seq_setting = sys.argv[3]
        check_event = sys.argv[4].lower() == 'true'
        check_seq = sys.argv[5].lower() == 'true'

        result = validate_qr(qr_input, target_event, seq_setting, check_event, check_seq)

    # 重要: 辞書型をJSON文字列に変換して出力
    print(json.dumps(result, ensure_ascii=False))

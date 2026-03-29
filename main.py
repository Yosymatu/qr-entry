
# -*- coding: utf-8 -*-
"""
QR Gate Checker (CustomTkinter) - spec 2026/02
- QR仕様：チェックNo_イベント名_券種_ロット_連番_乱数
- 判定：チェックNo/イベント名の厳密一致。不一致→NG
- 直前と同一文字列が1秒以内に再入力→無視（判定なし）
- ログはDBへ蓄積、CSV出力可
- 入力モード：HID（キーボード）/ Serial（USB-COM; 複数ポート同時対応）
"""
from __future__ import annotations
import os, sys
import io
import json
import sqlite3
import platform
import threading
import queue
from datetime import datetime, date, timedelta
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox
import polars as pl
from PIL import Image, ImageTk

# ---- Optional serial imports (for USB-COM mode) ----
try:
    import serial  # type: ignore
    from serial.tools import list_ports  # type: ignore
    _SERIAL_AVAILABLE = True
except Exception:
    serial = None  # type: ignore
    list_ports = None  # type: ignore
    _SERIAL_AVAILABLE = False

APP_TITLE = "QR Gate Checker"
DB_PATH = os.path.join("data", "logs.db")
ASSETS_DIR = "assets"
OK_SOUND = os.path.join(ASSETS_DIR, "ok.wav")
NG_SOUND = os.path.join(ASSETS_DIR, "ng.wav")
SETTINGS_PATH = os.path.join("data", "settings.json")

# 既定テーマ（視認性優先で Light を既定に）
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")

# 券種コード（仕様）
TICKET_TYPE_LABEL = {
    "01": "大人/一般/600",
    "11": "大人/一般/1000",
    "02": "大人/団体",
    "03": "子ども/一般",
    "04": "子ども/団体",
    "05": "市民優待",
}

# ===== DB =====
def ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                qr_text TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT
            )
            """
        )
        conn.commit()

def insert_log(qr_text: str, status: str, reason: str | None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO logs (ts, qr_text, status, reason) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), qr_text, status, reason),
        )
        conn.commit()

def export_csv_and_clear(filepath: str):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT ts, qr_text, status, reason FROM logs ORDER BY id")
        rows = cur.fetchall()
        schema = ["ts", "qr_text", "status", "reason"]
        if rows:
            df = pl.DataFrame(rows, schema=schema, orient="row")
        else:
            df = pl.DataFrame(schema=schema)
        buf = io.StringIO()
        df.write_csv(buf)
        csv_bytes = buf.getvalue().encode("utf-8")
        with open(filepath, "wb") as f:
            # UTF-8 BOM 付き（Excelでの文字化け回避）
            f.write(b"\xef\xbb\xbf" + csv_bytes)
        conn.execute("DELETE FROM logs")
        conn.commit()

# ユニーク件数

def get_unique_qr_count() -> int:
    """logs テーブルの qr_text のユニーク件数（重複なしの実数）を返す"""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT COUNT(DISTINCT qr_text) FROM logs")
        (cnt,) = cur.fetchone()
        return int(cnt or 0)

# ===== Utils =====

def today_str_local() -> str:
    return date.today().strftime("%Y-%m-%d")


# ---- WAV 再生バックエンド検出 ----
_AUDIO_BACKEND = None
try:
    import winsound  # type: ignore
    _AUDIO_BACKEND = "winsound"
except ImportError:
    # Windows以外の環境など、winsoundがインポートできない場合は無音になります
    _AUDIO_BACKEND = None

def safe_play_wav(path: str, enabled: bool):
    # 1. PyInstaller実行時でも確実にファイルを見つけるための絶対パス解決
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    abs_path = os.path.join(base, path)

    # 絶対パスでファイルの存在確認
    if not enabled or not os.path.exists(abs_path) or _AUDIO_BACKEND != "winsound":
        return

    # 2. スレッドを使わずに直接再生（SND_ASYNC自体がUIをブロックしないためスレッド不要）
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)  # type: ignore
        winsound.PlaySound(
            abs_path, winsound.SND_FILENAME | winsound.SND_ASYNC  # type: ignore
        )
    except Exception as e:
        print(f"[Audio Error] {e}")

# def safe_play_wav(path: str, enabled: bool):
#     if not enabled or not os.path.exists(path) or _AUDIO_BACKEND != "winsound":
#         return

#     def _play():
#         try:
#             # SND_PURGEで再生中の音を停止してから、SND_ASYNCで非同期再生
#             winsound.PlaySound(None, winsound.SND_PURGE)  # type: ignore
#             winsound.PlaySound(
#                 path, winsound.SND_FILENAME | winsound.SND_ASYNC  # type: ignore
#             )
#         except Exception as e:
#             print(f"[Audio Error] {e}")

#     # winsoundの非同期再生(SND_ASYNC)を利用しますが、
#     # メインスレッドのUIブロックを完全に防ぐため念のため別スレッドで発火します
#     threading.Thread(target=_play, daemon=True).start()

# # ---- WAV 再生バックエンド検出 ----
# _AUDIO_BACKEND = None  # "winsound" | "simpleaudio" | None
# try:
#     if platform.system() == "Windows":
#         import winsound  # type: ignore
#         _AUDIO_BACKEND = "winsound"
#     else:
#         try:
#             import simpleaudio as sa  # type: ignore
#             _AUDIO_BACKEND = "simpleaudio"
#         except Exception:
#             _AUDIO_BACKEND = None
# except Exception:
#     _AUDIO_BACKEND = None


# def safe_play_wav(path: str, enabled: bool):
#     if not enabled or not os.path.exists(path):
#         return

#     def _play():
#         try:
#             if _AUDIO_BACKEND == "winsound":
#                 try:
#                     winsound.PlaySound(None, winsound.SND_PURGE)  # type: ignore
#                 except Exception:
#                     pass
#                 winsound.PlaySound(
#                     path, winsound.SND_FILENAME | winsound.SND_ASYNC  # type: ignore
#                 )
#             elif _AUDIO_BACKEND == "simpleaudio":
#                 try:
#                     import simpleaudio as sa  # type: ignore
#                     sa.WaveObject.from_wave_file(path).play()
#                 except Exception:
#                     pass
#             else:
#                 # バックエンドなし: 無音
#                 pass
#         except Exception:
#             pass

#     threading.Thread(target=_play, daemon=True).start()

# ===== Serial (USB-COM) Reader =====

class SerialReader(threading.Thread):
    """1つのCOMポートを監視し、
/
で1件確定してキューへ送る。"""

    def __init__(self, port: str, baud: int, out_queue: "queue.Queue[tuple[str,str]]", label: str, eol: str = "auto"):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.out_queue = out_queue
        self.label = label  # 例:"Gate A"
        self.eol = (eol or "auto").lower()
        self._stop = threading.Event()

    def run(self):
        if not _SERIAL_AVAILABLE:
            return
        try:
            with serial.Serial(self.port, self.baud, timeout=0.1) as ser:  # type: ignore
                buf: list[str] = []
                while not self._stop.is_set():
                    b = ser.read(1)
                    if not b:
                        continue
                    try:
                        ch = b.decode(errors="ignore")
                    except Exception:
                        continue
                    if self._is_terminator(ch, buf):
                        text = "".join(buf).strip()
                        buf.clear()
                        if text:
                            self.out_queue.put((text, self.label))
                    else:
                        buf.append(ch)
        except Exception as e:
            print(f"[SerialReader:{self.label}] {e}")


    def _is_terminator(self, ch: str, buf: list[str]) -> bool:
        """行終端（CR/LF/CRLF/auto）の判定"""
        # eol=auto: CR または LF のどちらでも区切り
        if self.eol == "auto":
            return ch in ("\r", "\n")
        if self.eol == "cr":
            return ch == "\r"
        if self.eol == "lf":
            return ch == "\n"
        if self.eol == "crlf":
            # 簡易判定: 直前が CR で今回が LF
            return len(buf) > 0 and buf[-1] == "\r" and ch == "\n"
        # デフォルトは auto と同義
        return ch in ("\r", "\n")

    def stop(self):
        self._stop.set()

# ===== UI Helper =====

def jp_font(size: int, weight: str | None = None):
    try:
        return ctk.CTkFont(family="BIZ UDGothic", size=size, weight=weight)
    except Exception:
        return ctk.CTkFont(family="BIZ UDGothic", size=size, weight=weight)


def resource_path(rel_path: str) -> str:
    """PyInstaller実行時（_MEIPASS）でも資産を確実に参照"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel_path)


class Chip(ctk.CTkLabel):
    def __init__(self, master, text: str, fg="#1a1a1a", bg="#DADADA", font_size: int = 10):
        super().__init__(master, text=text, fg_color=bg, corner_radius=999, padx=12, pady=6)
        self.configure(text_color=fg, font=jp_font(font_size, "bold"))


class IconButton(ctk.CTkButton):
    def __init__(self, master, text: str, command=None, width=48, height=44, tooltip: str | None = None):
        super().__init__(master, text=text, width=width, height=height, command=command)
        if tooltip:
            self._tip = ctk.CTkLabel(master, text=tooltip, fg_color="#333333", corner_radius=6)
            self._tip_visible = False

            def _enter(_):
                if not self._tip_visible:
                    self._tip.place(in_=self, relx=0.5, rely=0, y=-32, anchor="s")
                    self._tip_visible = True

            def _leave(_):
                if self._tip_visible:
                    self._tip.place_forget()
                    self._tip_visible = False

            self.bind("<Enter>", _enter)
            self.bind("<Leave>", _leave)


class Toast(ctk.CTkFrame):
    def __init__(self, master, message: str, duration_ms: int = 1800):
        super().__init__(master, fg_color="#2d2d2d", corner_radius=10)
        self.label = ctk.CTkLabel(self, text=message, font=jp_font(20, "bold"))
        self.label.pack(padx=14, pady=12)
        self.duration_ms = duration_ms

    def show(self):
        self.update_idletasks()
        w = 360
        h = 52
        x = self.master.winfo_width() - w - 24
        y = self.master.winfo_height() - h - 24
        self.place(x=x, y=y)
        self.configure(width=w, height=h)
        self.after(self.duration_ms, self.hide)

    def hide(self):
        self.place_forget()


# ===== Main App =====
class QRGateApp(ctk.CTk):
    _instance_guard = False

    def __init__(self):
        if QRGateApp._instance_guard:
            raise RuntimeError("App is already initialized")
        QRGateApp._instance_guard = True
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("1200x820")
        self.minsize(980, 700)
        ensure_db()

        # --- アイコン設定 ---
        try:
            png_path = resource_path("assets/app.png")
            if os.path.exists(png_path):
                img = Image.open(png_path)
                small = ImageTk.PhotoImage(img.resize((32, 32)))
                self.iconphoto(True, small)
            if sys.platform.startswith("win"):
                ico_path = resource_path("assets/app.ico")
                if os.path.exists(ico_path):
                    self.iconbitmap(ico_path)
        except Exception as e:
            print(f"[icon] set failed: {e}")

        # 設定・状態変数
        self.setting_check_number = tk.StringVar()
        self.setting_event_name = tk.StringVar()
        self.sound_enabled = tk.BooleanVar(value=True)
        self.is_fullscreen = tk.BooleanVar(value=False)
        self.appearance_mode = tk.StringVar(value="light")  # light/dark/system
        self.senior_mode = tk.BooleanVar(value=False)  # シニア表示

        # 入力モード/シリアル設定
        self.input_mode = tk.StringVar(value="serial")  # "hid" or "serial"
        self.serial_ports = tk.StringVar(value="")      # 例: "COM5,COM6" or "/dev/ttyUSB0,/dev/ttyUSB1"
        self.serial_baud = tk.IntVar(value=115200)
        self.serial_eol = tk.StringVar(value="auto")    # auto/cr/lf/crlf

        # 常時読み取り制御（HID用）
        self.always_scan_on = False
        self.scan_keep_focus_job = None
        self.scan_buffer = tk.StringVar()
        self.last_qr_text: str | None = None
        self.last_qr_time = datetime.min

        # Serial用（複数ポート）
        self.scan_queue: "queue.Queue[tuple[str,str]]" = queue.Queue()
        self.readers: list[SerialReader] = []
        self.last_by_source: dict[str, tuple[str, datetime]] = {}
        self.dequeue_job = None

        # レイアウト
        self.appbar = self._build_appbar()
        self.appbar.pack(side="top", fill="x")
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)
        self.screen_settings = SettingsScreen(self.container, self)
        self.screen_dashboard = DashboardScreen(self.container, self)

        # 設定ロード（UI作成後に反映）
        self.load_settings()
        self.screen_settings.pack(fill="both", expand=True)

        # UI適用（スケーリング/フォント/色）
        self.apply_ui_prefs()

        # キー操作
        self.bind("<F11>", lambda e: self.toggle_fullscreen())

        # 終了フック
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- AppBar ----
    def _build_appbar(self):
        bar = ctk.CTkFrame(self, height=64, corner_radius=0)
        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.pack(side="left", padx=12)
        mid = ctk.CTkFrame(bar, fg_color="transparent")
        mid.pack(side="left", padx=10, fill="x", expand=True)
        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right", padx=10)

        icon = ctk.CTkLabel(left, text="🗂", font=jp_font(20, "bold"))
        title = ctk.CTkLabel(left, text=APP_TITLE, font=jp_font(18, "bold"))
        icon.pack(side="left")
        title.pack(side="left", padx=(8, 0))
        self.breadcrumb = ctk.CTkLabel(mid, text="設定未開始", font=jp_font(10))
        self.breadcrumb.pack(side="left", padx=8)

        self.btn_settings = IconButton(right, text="⚙", tooltip="設定", command=self.go_settings)
        self.btn_settings.pack(side="right", padx=4, pady=8)
        self.btn_export = IconButton(right, text="📄", tooltip="CSV出力", command=self.on_export_csv)
        self.btn_export.pack(side="right", padx=4, pady=8)
        self.btn_full = IconButton(right, text="⛶", tooltip="全画面切替", command=self.toggle_fullscreen)
        self.btn_full.pack(side="right", padx=4, pady=8)
        self.btn_sound = IconButton(right, text="🔊", tooltip="サウンド切替", command=self.toggle_sound)
        self.btn_sound.pack(side="right", padx=4, pady=8)
        return bar

    def update_breadcrumb(self):
        chk = self.setting_check_number.get().strip() or "(未設定)"
        ev = self.setting_event_name.get().strip() or "(未設定)"
        mode = self.input_mode.get().upper()
        self.breadcrumb.configure(text=f"CHK: {chk}  /  EV: {ev}  /  MODE: {mode}")

    def toggle_sound(self):
        self.sound_enabled.set(not self.sound_enabled.get())
        self.btn_sound.configure(text="🔊" if self.sound_enabled.get() else "🔇")
        try:
            self.save_settings()
        except Exception:
            pass

    def toggle_fullscreen(self):
        state = not self.is_fullscreen.get()
        self.is_fullscreen.set(state)
        self.attributes("-fullscreen", state)
        self.btn_full.configure(text="⛶" if not state else "🗖")

    def set_appearance(self, mode: str):
        mode = (mode or "system").lower()
        if mode not in ("light", "dark", "system"):
            mode = "system"
        ctk.set_appearance_mode(mode)
        self.appearance_mode.set(mode)
        try:
            self.save_settings()
        except Exception:
            pass

    def on_export_csv(self):
        dest = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile=f"qr_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not dest:
            return
        try:
            export_csv_and_clear(dest)
            Toast(self, "CSVを出力し、ログを消去しました。").show()
            try:
                self.screen_dashboard.refresh_counter()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("CSV出力エラー", str(e))

    # ---- 設定保存/読込 ----
    def settings_to_dict(self) -> dict:
        return {
            "check_number": self.setting_check_number.get().strip(),
            "event_name": self.setting_event_name.get().strip(),
            "sound_enabled": bool(self.sound_enabled.get()),
            "appearance_mode": self.appearance_mode.get().lower(),
            "senior_mode": bool(self.senior_mode.get()),
            "input_mode": self.input_mode.get().lower(),
            "serial_ports": self.serial_ports.get().strip(),
            "serial_baud": int(self.serial_baud.get()),
            "serial_eol": self.serial_eol.get().lower(),
        }

    def apply_settings_from_dict(self, d: dict):
        self.setting_check_number.set(d.get("check_number", "") or "")
        self.setting_event_name.set(d.get("event_name", "") or "")
        self.sound_enabled.set(bool(d.get("sound_enabled", True)))
        mode = (d.get("appearance_mode") or "light").lower()
        self.set_appearance(mode)
        self.senior_mode.set(bool(d.get("senior_mode", False)))
        self.input_mode.set((d.get("input_mode") or "serial").lower())
        self.serial_ports.set(d.get("serial_ports", ""))
        try:
            self.serial_baud.set(int(d.get("serial_baud", 115200)))
        except Exception:
            self.serial_baud.set(115200)
        self.serial_eol.set((d.get("serial_eol") or "auto").lower())
        self.update_breadcrumb()

    def save_settings(self):
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(self.settings_to_dict(), f, ensure_ascii=False, indent=2)

    def load_settings(self):
        try:
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.apply_settings_from_dict(data)
        except Exception as e:
            messagebox.showwarning("設定読込エラー", f"settings.json の読込に失敗しました：{e}")

    def _on_close(self):
        try:
            self.save_settings()
        except Exception:
            pass
        # Stop serial readers
        self._stop_serial_readers()
        self.destroy()

    # ---- 画面遷移 ----
    def go_settings(self):
        self.always_scanning_off()
        self._stop_serial_readers()
        self.screen_dashboard.pack_forget()
        self.screen_settings.pack(fill="both", expand=True)
        self.breadcrumb.configure(text="設定画面（常時読み取り：OFF）")

    def go_dashboard_and_start(self):
        if not self.setting_check_number.get().strip() or not self.setting_event_name.get().strip():
            messagebox.showwarning("未入力", "チェックナンバーとイベント名を入力してください。")
            return
        self.screen_settings.pack_forget()
        self.screen_dashboard.pack(fill="both", expand=True)
        self.update_breadcrumb()
        self.screen_dashboard.show_waiting()
        self.save_settings()  # スナップショット保存

        # 入力モードで切替
        if self.input_mode.get().lower() == "serial":
            if not _SERIAL_AVAILABLE:
                messagebox.showerror("Serial未導入", "pyserial が見つかりません。pip install pyserial を実施してください。")
                return
            started = self._start_serial_readers()
            if not started:
                return
        else:
            self.always_scanning_on()

    # ---- HID: 常時読み取り（従来方式; フォールバック用） ----
    def always_scanning_on(self):
        if self.always_scan_on:
            return
        self.always_scan_on = True
        self.scan_buffer.set("")
        self.screen_dashboard.focus_scanner()
        self.keep_focus_loop()

    def always_scanning_off(self):
        self.always_scan_on = False
        if self.scan_keep_focus_job:
            self.after_cancel(self.scan_keep_focus_job)
            self.scan_keep_focus_job = None

    def keep_focus_loop(self):
        if not self.always_scan_on:
            return
        self.screen_dashboard.focus_scanner()
        self.scan_keep_focus_job = self.after(250, self.keep_focus_loop)

    def on_enter_pressed(self):
        if not self.always_scan_on:
            return
        text = self.scan_buffer.get().strip()
        self.scan_buffer.set("")
        if not text:
            return
        now = datetime.now()
        # --- 重複防止：同一文字列が1秒以内なら無視（判定なし） ---
        if self.last_qr_text == text and (now - self.last_qr_time).total_seconds() < 1.0:
            return
        self.last_qr_text = text
        self.last_qr_time = now
        status, reason = self.evaluate_qr(text)
        self.screen_dashboard.show_result(status, reason, source_label="HID")
        insert_log(f"[HID] {text}", status, None if status == "OK" else reason)
        try:
            self.screen_dashboard.refresh_counter()
        except Exception:
            pass
        safe_play_wav(OK_SOUND if status == "OK" else NG_SOUND, self.sound_enabled.get())
        self.after(1000, self.screen_dashboard.show_waiting)

    # ---- Serial: 起動/停止/デキュー ----
    def _parse_ports(self) -> list[str]:
        s = (self.serial_ports.get() or "").strip()
        if not s:
            return []
        return [p.strip() for p in s.split(",") if p.strip()]

    def _start_serial_readers(self) -> bool:
        ports = self._parse_ports()
        if not ports:
            # 自動列挙して案内
            if list_ports is not None:
                avail = [p.device for p in list_ports.comports()]
            else:
                avail = []
            messagebox.showwarning(
                "ポート未設定",
                "シリアルポートが未設定です。設定>入力 で COMポートを指定してください。"
                f"検出: {', '.join(avail) if avail else '(検出不可)'}",
            )
            return False
        # Start readers
        self._stop_serial_readers()
        self.readers = []
        label_seq = 65  # 'A'
        for port in ports:
            label = f"Device {chr(label_seq)}"
            label_seq += 1
            r = SerialReader(port, int(self.serial_baud.get()), self.scan_queue, label, eol=self.serial_eol.get())
            r.start()
            self.readers.append(r)
        # Start dequeue loop
        self._schedule_dequeue()
        return True

    def _stop_serial_readers(self):
        # cancel dequeue loop
        if self.dequeue_job is not None:
            try:
                self.after_cancel(self.dequeue_job)
            except Exception:
                pass
            self.dequeue_job = None
        for r in self.readers:
            try:
                r.stop()
            except Exception:
                pass
        self.readers.clear()

    def _schedule_dequeue(self):
        try:
            while True:
                text, source = self.scan_queue.get_nowait()
                now = datetime.now()
                # source別に重複防止
                last = self.last_by_source.get(source)
                if last and last[0] == text and (now - last[1]).total_seconds() < 1.0:
                    continue
                self.last_by_source[source] = (text, now)

                status, reason = self.evaluate_qr(text)
                self.screen_dashboard.show_result(status, reason, source_label=source)
                insert_log(f"[{source}] {text}", status, None if status == "OK" else reason)
                try:
                    self.screen_dashboard.refresh_counter()
                except Exception:
                    pass
                safe_play_wav(OK_SOUND if status == "OK" else NG_SOUND, self.sound_enabled.get())
                # 画面を待機状態に戻す（短時間で連続入力を邪魔しないよう短め）
                self.after(700, self.screen_dashboard.show_waiting)
        except queue.Empty:
            pass
        finally:
            self.dequeue_job = self.after(10, self._schedule_dequeue)

    # ---- 判定ロジック（仕様準拠; ロット不使用） ----
    def evaluate_qr(self, qr_text: str) -> tuple[str, str | None]:
        """
        フォーマット：チェックNo_イベント名_券種_ロット_連番_乱数
        - チェックNo/イベント名：設定値と厳密一致
        - 券種：01/11/02/03/04/05（未知値はNG）
        - ※ロット番号は判定に使用しない
        """
        parts = qr_text.split("_")
        if len(parts) != 6:
            return "NG", "フォーマット不正（要素数は6）"
        check_no, event_name, ticket_type, lot_no, seq, rand_part = parts
        # 入力設定との厳密照合
        if check_no != (self.setting_check_number.get().strip()):
            return "NG", "チェックナンバー不一致"
        if event_name != (self.setting_event_name.get().strip()):
            return "NG", "イベント名不一致"
        # 券種バリデーション
        if ticket_type not in TICKET_TYPE_LABEL:
            return "NG", f"券種不明（{ticket_type}）"
        # ※ロット番号は合否に影響させない
        return "OK", None

    # ---- UI適用（スケール/フォント/色まとめ） ----
    def apply_ui_prefs(self):
        # スケーリング
        if self.senior_mode.get():
            ctk.set_widget_scaling(1.5)  # ウィジェット寸法拡大
            ctk.set_window_scaling(1.2)  # 文字/描画のスケール
        else:
            ctk.set_widget_scaling(1.0)
            ctk.set_window_scaling(1.0)
        # AppBarのフォント微調整
        self.breadcrumb.configure(font=jp_font(10))
        # 主要画面ラベルの文字サイズ調整
        try:
            self.screen_dashboard.status_label.configure(font=jp_font(50 if self.senior_mode.get() else 50, "bold"))
            self.screen_dashboard.reason_label.configure(font=jp_font(24 if self.senior_mode.get() else 20))
        except Exception:
            pass
        # 保存
        try:
            self.save_settings()
        except Exception:
            pass


# ===== 設定画面 =====
class SettingsScreen(ctk.CTkFrame):
    def __init__(self, parent, app: QRGateApp):
        super().__init__(parent)
        self.app = app

        header = ctk.CTkLabel(self, text="イベント設定", font=jp_font(20, "bold"))
        header.pack(pady=(20, 10), anchor="w", padx=16)

        tabs = ctk.CTkTabview(self, segmented_button_fg_color="#DADADA")
        tabs.pack(fill="both", expand=True, padx=24, pady=(15, 9))
        tab_event = tabs.add("イベント")
        tab_input = tabs.add("入力")
        tab_view = tabs.add("表示・音")
        tab_info = tabs.add("仕様メモ")
        tabs._segmented_button.configure(font=ctk.CTkFont(family="BIZ UDGothic", size=20, weight="bold"))

        # --- イベント ---
        row1 = ctk.CTkFrame(tab_event)
        row1.pack(fill="x", pady=8, padx=8)
        ctk.CTkLabel(row1, text="チェックナンバー", width=160, anchor="w", font=jp_font(20)).pack(side="left", padx=6)
        ctk.CTkEntry(row1, textvariable=self.app.setting_check_number, width=300).pack(side="left", padx=6)

        row2 = ctk.CTkFrame(tab_event)
        row2.pack(fill="x", pady=8, padx=8)
        ctk.CTkLabel(row2, text="イベント名", width=160, anchor="w", font=jp_font(20)).pack(side="left", padx=6)
        ctk.CTkEntry(row2, textvariable=self.app.setting_event_name, width=300).pack(side="left", padx=6)

        ctk.CTkLabel(
            tab_event, text="※設定画面では常時読み取りは無効です", text_color="gray", font=jp_font(18)
        ).pack(anchor="w", padx=12, pady=(4, 0))

        # --- 入力 ---
        rowm = ctk.CTkFrame(tab_input)
        rowm.pack(fill="x", pady=8, padx=8)
        ctk.CTkLabel(rowm, text="入力モード", width=160, anchor="w", font=jp_font(20)).pack(side="left", padx=6)
        seg = ctk.CTkSegmentedButton(rowm, values=["serial", "hid"], command=lambda v: self._on_mode_change(v))
        seg.set(self.app.input_mode.get())
        seg.pack(side="left", padx=6)

        rowp = ctk.CTkFrame(tab_input)
        rowp.pack(fill="x", pady=8, padx=8)
        ctk.CTkLabel(rowp, text="シリアルポート（カンマ区切り）", width=220, anchor="w", font=jp_font(20)).pack(side="left", padx=6)
        ctk.CTkEntry(rowp, textvariable=self.app.serial_ports, width=380).pack(side="left", padx=6)
        ctk.CTkButton(rowp, text="ポート一覧", command=self._list_ports, width=110).pack(side="left", padx=6)

        rowb = ctk.CTkFrame(tab_input)
        rowb.pack(fill="x", pady=8, padx=8)
        ctk.CTkLabel(rowb, text="ボーレート", width=160, anchor="w", font=jp_font(20)).pack(side="left", padx=6)
        ctk.CTkEntry(rowb, textvariable=self.app.serial_baud, width=160).pack(side="left", padx=6)

        rowe = ctk.CTkFrame(tab_input)
        rowe.pack(fill="x", pady=8, padx=8)
        ctk.CTkLabel(rowe, text="改行（区切り）", width=160, anchor="w", font=jp_font(20)).pack(side="left", padx=6)
        seg2 = ctk.CTkSegmentedButton(rowe, values=["auto", "cr", "lf", "crlf"], command=lambda v: self._on_eol_change(v))
        seg2.set(self.app.serial_eol.get())
        seg2.pack(side="left", padx=6)

        # --- 表示・音 ---
        rowa = ctk.CTkFrame(tab_view)
        rowa.pack(fill="x", pady=8, padx=8)
        ctk.CTkLabel(rowa, text="外観（Light / Dark / System）", width=260, anchor="w", font=jp_font(20)).pack(
            side="left", padx=6
        )
        segv = ctk.CTkSegmentedButton(rowa, values=["light", "dark", "system"], command=lambda v: self.app.set_appearance(v))
        segv.set(self.app.appearance_mode.get())
        segv.pack(side="left", padx=6)

        rows = ctk.CTkFrame(tab_view)
        rows.pack(fill="x", pady=8, padx=8)
        ctk.CTkLabel(rows, text="シニア表示（大きい文字・高コントラスト）", width=260, anchor="w", font=jp_font(20)).pack(
            side="left", padx=6
        )
        ctk.CTkSwitch(
            rows,
            text="ON/OFF",
            variable=self.app.senior_mode,
            onvalue=True,
            offvalue=False,
            command=self.app.apply_ui_prefs,
        ).pack(side="left", padx=6)

        row_sound = ctk.CTkFrame(tab_view)
        row_sound.pack(fill="x", pady=8, padx=8)
        ctk.CTkLabel(row_sound, text="サウンド", width=160, anchor="w", font=jp_font(20)).pack(side="left", padx=6)
        ctk.CTkSwitch(
            row_sound,
            text="有効/無効",
            variable=self.app.sound_enabled,
            onvalue=True,
            offvalue=False,
            command=lambda: self.app.save_settings(),
        ).pack(side="left", padx=6)

        # --- 仕様メモ（読み取り時のヒント） ---
        info = ctk.CTkTextbox(tab_info, height=220)
        info.pack(fill="both", expand=True, padx=8, pady=8)
        memo = []
        memo.append("【QRコード仕様】")
        memo.append("チェックNo_イベント名_券種_ロット_連番_乱数")
        memo.append("券種：01=大人/一般/600, 11=大人/一般/1000, 02=大人/団体, 03=子ども/一般, 04=子ども/団体, 05=市民優待")
        memo.append("")
        memo.append("【重複防止】")
        memo.append("直前と同一文字列を1秒以内に再入力した場合は無視（判定なし）")
        memo.append("")
        memo.append("【入力モード】")
        memo.append("Serial: 複数ポート同時読取に対応。HID: 既存のキーボードウェッジ方式。")
        info.insert("1.0", "".join(memo))
        info.configure(state="disabled")

        # --- Actions ---
        actions = ctk.CTkFrame(self)
        actions.pack(pady=12)
        ctk.CTkButton(
            actions, text="保存", width=140, height=40, command=self.app.save_settings, font=jp_font(25, "bold")
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            actions, text="開始", width=160, height=40, command=self.app.go_dashboard_and_start, font=jp_font(25, "bold")
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            actions, text="終了", width=140, height=40, fg_color="#444444", command=self.app.destroy, font=jp_font(25, "bold")
        ).pack(side="left", padx=8)

    def _on_mode_change(self, v: str):
        self.app.input_mode.set(v)
        self.app.save_settings()

    def _on_eol_change(self, v: str):
        self.app.serial_eol.set(v)
        self.app.save_settings()

    def _list_ports(self):
        if not _SERIAL_AVAILABLE:
            messagebox.showerror("Serial未導入", "pyserial が見つかりません。pip install pyserial を実施してください。")
            return
        ports = list_ports.comports() if list_ports else []
        if not ports:
            messagebox.showinfo("ポート一覧", "シリアルポートが見つかりませんでした。")
            return
        msg = "".join([f"{p.device} : {p.description}" for p in ports])
        messagebox.showinfo("ポート一覧", msg)


# ===== ダッシュボード =====
class DashboardScreen(ctk.CTkFrame):
    def __init__(self, parent, app: QRGateApp):
        super().__init__(parent)
        self.app = app
        # 上部チップ行
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=16, pady=(16, 10))
        self.chip_chk = Chip(top, text="CHK: -", bg="#E6F0FF", fg="#0A2B6B", font_size=8)
        self.chip_ev  = Chip(top, text="EV: -",  bg="#E6F0FF", fg="#0A2B6B", font_size=8)
        self.chip_mode = Chip(top, text="MODE: -", bg="#EDE7FF", fg="#2F1372", font_size=8)
        self.chip_snd = Chip(top, text="SOUND: ON", bg="#FFEBD6", fg="#6B2E0A", font_size=8)
        self.chip_cnt = Chip(top, text="COUNT: 0", bg="#EAF7FF", fg="#003A63", font_size=8)
        for w in (self.chip_chk, self.chip_ev, self.chip_mode, self.chip_snd, self.chip_cnt):
            w.pack(side="left", padx=6, pady=6)

        # 判定カード
        self.card = ctk.CTkFrame(self, corner_radius=14)
        self.card.pack(fill="both", expand=True, padx=18, pady=10)
        self.status_label = ctk.CTkLabel(self.card, text="待機中", font=jp_font(72, "bold"))
        self.status_label.pack(pady=(64, 12))
        self.reason_label = ctk.CTkLabel(self.card, text="", font=jp_font(24))
        self.reason_label.pack()

        # 待機インジケータ
        self.wait_bar = ctk.CTkProgressBar(self.card, mode="indeterminate", height=22)
        self.wait_bar.pack(pady=(28, 20), padx=100, fill="x")

        # 隠し入力（HID用）
        self.scanner_entry = ctk.CTkEntry(self, textvariable=self.app.scan_buffer, width=1)
        self.scanner_entry.place(x=-1000, y=-1000)
        self.scanner_entry.bind("<KeyPress>", self.on_keypress)
        self.scanner_entry.bind("<Return>", self.on_return)
        # 貼り付けによるスキャン
        self.scanner_entry.bind("<<Paste>>", self.on_paste)
        self.scanner_entry.bind("<Control-v>", self.on_paste)
        self.scanner_entry.bind("<Command-v>", self.on_paste)

        self.show_waiting()

    def focus_scanner(self):
        self.scanner_entry.focus_set()

    def on_keypress(self, event):
        pass

    def on_return(self, event):
        self.app.on_enter_pressed()

    def on_paste(self, event):
        if not self.app.always_scan_on:
            return
        def _after():
            text = self.app.scan_buffer.get().strip()
            if text:
                self.app.on_enter_pressed()
        self.after_idle(_after)

    def _pick(self, light: str, dark: str) -> str:
        mode = self.app.appearance_mode.get().lower()
        if mode == "dark":
            return dark
        if mode == "system":
            try:
                current = ctk.get_appearance_mode().lower()
                return dark if current == "dark" else light
            except Exception:
                return light
        return light

    def show_waiting(self):
        self.configure(fg_color=(self._pick("#F5F5F5", "#171717")))
        self.status_label.configure(text="待機中", text_color=self._pick("#1A1A1A", "white"))
        self.reason_label.configure(text="", text_color=self._pick("#333333", "#E0E0E0"))
        self.wait_bar.start()
        # チップ更新
        self.chip_chk.configure(text=f"CHK: {self.app.setting_check_number.get() or '-'}")
        self.chip_ev.configure(text=f"EV: {self.app.setting_event_name.get() or '-'}")
        self.chip_mode.configure(text=f"MODE: {self.app.input_mode.get().upper()}")
        self.chip_snd.configure(text=f"SOUND: {'ON' if self.app.sound_enabled.get() else 'OFF'}")
        self.refresh_counter()

    def refresh_counter(self):
        try:
            cnt = get_unique_qr_count()
        except Exception:
            cnt = 0
        self.chip_cnt.configure(text=f"COUNT: {cnt}")

    def show_result(self, status: str, reason: str | None, source_label: str | None = None):
        self.wait_bar.stop()
        if status == "OK":
            # 高コントラスト緑
            bg1 = self._pick("#DFF5E1", "#117733")
            bg2 = self._pick("#CBEBD0", "#0a4d22")
            self.flash_bg(bg1, bg2)
            self.status_label.configure(text="OK", text_color=self._pick("#046A38", "#a6ffb5"))
            src = f"（{source_label}）" if source_label else ""
            self.reason_label.configure(text=f"入場可能{src}", text_color=self._pick("#1A1A1A", "#E6FFE9"))
        else:
            # 高コントラスト赤
            bg1 = self._pick("#FCE4E4", "#8b1a1a")
            bg2 = self._pick("#F7D6D6", "#5c1010")
            self.flash_bg(bg1, bg2)
            self.status_label.configure(text="NG", text_color=self._pick("#8A0000", "#ffb3b3"))
            src = f"（{source_label}）" if source_label else ""
            self.reason_label.configure(text=(reason or "不明なエラー") + src, text_color=self._pick("#1A1A1A", "#FFECEC"))

    def flash_bg(self, color1: str, color2: str):
        self.configure(fg_color=color1)
        self.after(140, lambda: self.configure(fg_color=color2))


# ===== エントリーポイント =====
if __name__ == "__main__":
    app = QRGateApp()
    app.mainloop()

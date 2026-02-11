# -*- coding: utf-8 -*-
"""
QR Gate Checker (CustomTkinter) - spec 2026/02
- QR仕様：チェックNo_イベント名_券種_ロット_連番_乱数
- 判定：チェックNo/イベント名の厳密一致。不一致→NG
- （大人/一般=01のみ）ロット判定：本日許可ロット（奇数日=001 / 偶数日=002）と文字列一致
- 直前と同一文字列が1秒以内に再入力→無視（判定なし）
- ログはDBへ蓄積、CSV出力可

uv run python -m nuitka --standalone --enable-plugin=tk-inter --windows-console-mode=disable --include-data-dir=assets=assets --include-data-dir=data=data --include-package=customtkinter -o QRGateChecker.exe main.py
"""

from __future__ import annotations
import os, sys
import io
import json
import sqlite3
import platform
import threading
from datetime import datetime, date
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox
import polars as pl
from PIL import Image, ImageTk

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
    "01": "大人/一般",
    "02": "大人/団体",
    "03": "子ども/一般",
    "04": "子ども/団体",
    "05": "市民優待",
}
REQUIRES_LOT_CHECK = {"01"}  # ロット判定を行う券種（大人/一般のみ）


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


# ===== Utils =====
def today_str_local() -> str:
    return date.today().strftime("%Y-%m-%d")


def today_allowed_lot() -> str:
    """奇数日=001 / 偶数日=002"""
    return "001" if (date.today().day % 2 == 1) else "002"


# ---- WAV 再生バックエンド検出 ----
_AUDIO_BACKEND = None  # "winsound" | "simpleaudio" | None
try:
    if platform.system() == "Windows":
        import winsound  # type: ignore

        _AUDIO_BACKEND = "winsound"
    else:
        try:
            import simpleaudio as sa  # type: ignore

            _AUDIO_BACKEND = "simpleaudio"
        except Exception:
            _AUDIO_BACKEND = None
except Exception:
    _AUDIO_BACKEND = None


def safe_play_wav(path: str, enabled: bool):
    if not enabled or not os.path.exists(path):
        return

    def _play():
        try:
            if _AUDIO_BACKEND == "winsound":
                try:
                    winsound.PlaySound(None, winsound.SND_PURGE)  # type: ignore
                except Exception:
                    pass
                winsound.PlaySound(
                    path, winsound.SND_FILENAME | winsound.SND_ASYNC  # type: ignore
                )
            elif _AUDIO_BACKEND == "simpleaudio":
                try:
                    import simpleaudio as sa  # type: ignore

                    sa.WaveObject.from_wave_file(path).play()
                except Exception:
                    pass
            else:
                # バックエンドなし: 無音
                pass
        except Exception:
            pass

    threading.Thread(target=_play, daemon=True).start()


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
    def __init__(self, master, text: str, fg="#1a1a1a", bg="#DADADA", font_size: int = 20):
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
        self.senior_mode = tk.BooleanVar(value=True)  # シニア表示

        # 常時読み取り制御
        self.always_scan_on = False
        self.scan_keep_focus_job = None
        self.scan_buffer = tk.StringVar()
        self.last_qr_text: str | None = None
        self.last_qr_time = datetime.min

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

        icon = ctk.CTkLabel(left, text="🗂", font=jp_font(39, "bold"))
        title = ctk.CTkLabel(left, text=APP_TITLE, font=jp_font(36, "bold"))
        icon.pack(side="left")
        title.pack(side="left", padx=(8, 0)) 

        self.breadcrumb = ctk.CTkLabel(mid, text="設定未開始", font=jp_font(20))
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
        lot = today_allowed_lot()
        self.breadcrumb.configure(text=f"")

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
        }

    def apply_settings_from_dict(self, d: dict):
        self.setting_check_number.set(d.get("check_number", "") or "")
        self.setting_event_name.set(d.get("event_name", "") or "")
        self.sound_enabled.set(bool(d.get("sound_enabled", True)))
        mode = (d.get("appearance_mode") or "light").lower()
        self.set_appearance(mode)
        self.senior_mode.set(bool(d.get("senior_mode", True)))
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
        self.destroy()

    # ---- 画面遷移 ----
    def go_settings(self):
        self.always_scanning_off()
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
        self.always_scanning_on()

    # ---- 常時読み取り ----
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
        self.screen_dashboard.show_result(status, reason)
        insert_log(text, status, None if status == "OK" else reason)
        safe_play_wav(OK_SOUND if status == "OK" else NG_SOUND, self.sound_enabled.get())
        self.after(1000, self.screen_dashboard.show_waiting)

    # ---- 判定ロジック（仕様準拠） ----
    def evaluate_qr(self, qr_text: str) -> tuple[str, str | None]:
        """
        フォーマット：チェックNo_イベント名_券種_ロット_連番_乱数
        - チェックNo/イベント名：設定値と厳密一致
        - 券種：01/02/03/04/05（未知値はNG）
        - ロット判定：券種01のみ、本日許可ロット（奇数日001/偶数日002）と一致
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

        # 大人/一般のみロット判定
        if ticket_type in REQUIRES_LOT_CHECK:
            allowed = today_allowed_lot()
            if lot_no != allowed:
                return "NG", f"ロット番号非該当（本日許可: {allowed}）"

        # 上記以外はOK
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
        self.breadcrumb.configure(font=jp_font(20))

        # 主要画面ラベルの文字サイズ調整
        try:
            self.screen_dashboard.status_label.configure(font=jp_font(72 if self.senior_mode.get() else 54, "bold"))
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

        # --- 表示・音 ---
        rowa = ctk.CTkFrame(tab_view)
        rowa.pack(fill="x", pady=8, padx=8)
        ctk.CTkLabel(rowa, text="外観（Light / Dark / System）", width=260, anchor="w", font=jp_font(20)).pack(
            side="left", padx=6
        )
        seg = ctk.CTkSegmentedButton(rowa, values=["light", "dark", "system"], command=lambda v: self.app.set_appearance(v))
        seg.set(self.app.appearance_mode.get())
        seg.pack(side="left", padx=6)

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
        memo.append("券種：01=大人/一般, 02=大人/団体, 03=子ども/一般, 04=子ども/団体, 05=市民優待")
        memo.append("")
        memo.append("【本日許可ロット】")
        memo.append("奇数日：001 / 偶数日：002")
        memo.append("※ロット判定は券種01（大人/一般）のみ実施")
        memo.append("")
        memo.append("【重複防止】")
        memo.append("直前と同一文字列を1秒以内に再入力した場合は無視（判定なし）")
        info.insert("1.0", "\n".join(memo))
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


# ===== ダッシュボード =====
class DashboardScreen(ctk.CTkFrame):
    def __init__(self, parent, app: QRGateApp):
        super().__init__(parent)
        self.app = app

        # 上部チップ行
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=16, pady=(16, 10))
        self.chip_chk = Chip(top, text="CHK: -", bg="#E6F0FF", fg="#0A2B6B", font_size=16)
        self.chip_ev = Chip(top, text="EV: -", bg="#E6F0FF", fg="#0A2B6B", font_size=16)
        # self.chip_day = Chip(top, text=f"本日: {today_str_local()}", bg="#F0F0F0", fg="#1A1A1A", font_size=16)
        self.chip_lot = Chip(top, text=f"許可ロット: {today_allowed_lot()}", bg="#EDE7FF", fg="#2F1372", font_size=16)
        self.chip_snd = Chip(top, text="SOUND: ON", bg="#FFEBD6", fg="#6B2E0A", font_size=16)
        # for w in (self.chip_chk, self.chip_ev, self.chip_day, self.chip_lot, self.chip_snd):
        for w in (self.chip_chk, self.chip_ev, self.chip_lot, self.chip_snd):
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

        # 隠し入力
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
        # self.chip_day.configure(text=f"本日: {today_str_local()}")
        self.chip_lot.configure(text=f"許可ロット: {today_allowed_lot()}")
        self.chip_snd.configure(text=f"SOUND: {'ON' if self.app.sound_enabled.get() else 'OFF'}")

    def show_result(self, status: str, reason: str | None):
        self.wait_bar.stop()
        if status == "OK":
            # 高コントラスト緑
            bg1 = self._pick("#DFF5E1", "#117733")
            bg2 = self._pick("#CBEBD0", "#0a4d22")
            self.flash_bg(bg1, bg2)
            self.status_label.configure(text="OK", text_color=self._pick("#046A38", "#a6ffb5"))
            self.reason_label.configure(text="入場可能", text_color=self._pick("#1A1A1A", "#E6FFE9"))
        else:
            # 高コントラスト赤
            bg1 = self._pick("#FCE4E4", "#8b1a1a")
            bg2 = self._pick("#F7D6D6", "#5c1010")
            self.flash_bg(bg1, bg2)
            self.status_label.configure(text="NG", text_color=self._pick("#8A0000", "#ffb3b3"))
            self.reason_label.configure(text=reason or "不明なエラー", text_color=self._pick("#1A1A1A", "#FFECEC"))

    def flash_bg(self, color1: str, color2: str):
        self.configure(fg_color=color1)
        self.after(140, lambda: self.configure(fg_color=color2))


# ===== エントリーポイント =====
if __name__ == "__main__":
    app = QRGateApp()
    app.mainloop()
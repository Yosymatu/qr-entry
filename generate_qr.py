import tkinter as tk
from tkinter import Label
import qrcode
from PIL import ImageTk
import base64
import math
import time
import threading
import zlib

# --- 設定 ---
FILE_PATH = "secret.txt"   # 送信したいファイル
CHUNK_SIZE = 200           # 1つのQRコードに含める文字数（画質に合わせて調整）
FPS = 5                    # 1秒間の切り替え回数（カメラ性能に合わせて調整。3~10推奨）

class QRAnimateApp:
    def __init__(self, master, data_chunks):
        self.master = master
        self.master.title("Animated QR Sender")
        self.data_chunks = data_chunks
        self.total_chunks = len(data_chunks)
        self.current_index = 0
        self.running = False
        
        self.label = Label(master)
        self.label.pack()
        
        self.info_label = Label(master, text="Ready", font=("Arial", 16))
        self.info_label.pack()
        
        self.start_button = tk.Button(master, text="Start Loop", command=self.start_loop)
        self.start_button.pack()

    def generate_qr_image(self, data):
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_L, # L:7% (画質優先)
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        return ImageTk.PhotoImage(img)

    def start_loop(self):
        self.running = True
        thread = threading.Thread(target=self.animate)
        thread.daemon = True
        thread.start()

    def animate(self):
        while self.running:
            # データの形式: "index/total|payload"
            # 例: "001/050|SGVsbG8gV29ybGQ..."
            raw_payload = self.data_chunks[self.current_index]
            header = f"{self.current_index + 1:03d}/{self.total_chunks:03d}|"
            full_data = header + raw_payload
            
            # 画像生成と更新
            img = self.generate_qr_image(full_data)
            
            # GUIスレッドでの更新
            self.label.config(image=img)
            self.label.image = img
            self.info_label.config(text=f"Chunk: {self.current_index + 1} / {self.total_chunks}")
            
            self.current_index = (self.current_index + 1) % self.total_chunks
            time.sleep(1.0 / FPS)

def prepare_data(filepath):
    with open(filepath, "rb") as f:
        data = f.read()
    
    # 圧縮（効率化のため）
    compressed_data = zlib.compress(data)
    # Base64エンコード
    b64_data = base64.b64encode(compressed_data).decode('utf-8')
    
    chunks = []
    num_chunks = math.ceil(len(b64_data) / CHUNK_SIZE)
    
    for i in range(num_chunks):
        chunks.append(b64_data[i*CHUNK_SIZE : (i+1)*CHUNK_SIZE])
    
    return chunks

if __name__ == "__main__":
    root = tk.Tk()
    chunks = prepare_data(FILE_PATH)
    app = QRAnimateApp(root, chunks)
    root.mainloop()

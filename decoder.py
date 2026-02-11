import cv2
from pyzbar.pyzbar import decode
import base64
import os

# --- 設定 ---
VIDEO_PATH = "video.mp4"          # 撮影した動画ファイル名
OUTPUT_FILE = "restored_file.txt" # 復元後のファイル名

def main():
    cap = cv2.VideoCapture(VIDEO_PATH)
    
    if not cap.isOpened():
        print("動画ファイルが開けません")
        return

    print("解析開始...（Ctrl+C で強制保存可能）")
    
    collected_chunks = {} # {index: payload}
    total_chunks = None
    frame_count = 0
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_count += 1
            if frame_count % 30 == 0:
                print(f"処理中フレーム: {frame_count} | 取得済み: {len(collected_chunks)}/{total_chunks if total_chunks else '?'}")

            decoded_objects = decode(frame)
            
            for obj in decoded_objects:
                try:
                    text = obj.data.decode('utf-8')
                    # フォーマット "index/total|payload" を解析
                    if "|" in text:
                        header, payload = text.split("|", 1)
                        if "/" in header:
                            idx_str, total_str = header.split("/")
                            index = int(idx_str) - 1
                            total = int(total_str)
                            
                            if total_chunks is None:
                                total_chunks = total
                                print(f"データ検出: 全 {total_chunks} チャンク")
                            
                            if index not in collected_chunks:
                                collected_chunks[index] = payload
                                print(f"取得: {index + 1}/{total}")
                except:
                    pass
            
            # 全て揃ったら終了
            if total_chunks is not None and len(collected_chunks) == total_chunks:
                print("全てのデータチャンクが揃いました！")
                break

    except KeyboardInterrupt:
        print("\nユーザー中断。現時点のデータで保存します。")
    
    cap.release()

    if not collected_chunks:
        print("QRコードが見つかりませんでした。")
        return

    print("-" * 30)
    print("データを結合中...")

    # 欠損があっても結合する
    full_b64 = ""
    max_index = total_chunks if total_chunks else max(collected_chunks.keys()) + 1
    missing_count = 0

    for i in range(max_index):
        if i in collected_chunks:
            full_b64 += collected_chunks[i]
        else:
            print(f"警告: チャンク {i+1} が欠損しています")
            missing_count += 1

    if missing_count > 0:
        print(f"合計 {missing_count} 個のチャンクが足りませんが、強制的に復元します。")

    # === ここから変更点: Zlibを削除し、純粋なBase64デコードのみ実行 ===
    print("Base64デコード中...")
    
    try:
        # パディング（=）の補正（欠損などで長さが合わない場合の対策）
        missing_padding = len(full_b64) % 4
        if missing_padding:
            full_b64 += '=' * (4 - missing_padding)

        # validate=False で、万が一変な文字が混入していても無視して変換
        decoded_data = base64.b64decode(full_b64, validate=False)
        
        # 保存
        with open(OUTPUT_FILE, "wb") as f:
            f.write(decoded_data)
            
        print(f"完了: {OUTPUT_FILE} に保存しました。")
        print(f"復元サイズ: {len(decoded_data)} bytes")

    except Exception as e:
        print(f"デコードエラー: {e}")
        print("生データ（Base64テキスト）として保存します。")
        with open(OUTPUT_FILE + ".b64.txt", "w") as f:
            f.write(full_b64)

if __name__ == "__main__":
    main()
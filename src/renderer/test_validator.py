# -*- coding: utf-8 -*-
"""
validator.py の1000件テストスクリプト
"""
import sys
import os
import time
import random

# 出力エンコーディングを設定
sys.stdout.reconfigure(encoding='utf-8')

# validator.pyと同じディレクトリにあることを前提
from validator import validate_qr, init_db

def run_tests(num_tests=1000):
    """1000件のテストを実行"""

    # テスト用DBを初期化
    init_db()

    # テスト設定
    target_event = "SampleEvent"
    min_seq = 100
    check_event = True
    check_seq = True

    # 結果カウンター
    results = {
        "OK": 0,
        "NG": 0,
        "ERROR": 0
    }

    # 詳細なNG理由のカウント
    ng_reasons = {}

    print("=" * 60)
    print(f"テスト開始: {num_tests}件")
    print(f"設定: イベント名={target_event}, 下限連番={min_seq}")
    print(f"チェック: イベント名={check_event}, 連番={check_seq}")
    print("=" * 60)

    start_time = time.time()

    for i in range(num_tests):
        # テストデータ生成（様々なパターン）
        test_type = i % 10

        if test_type < 5:
            # 正常データ (50%): 正しいイベント名 + 有効な連番
            seq = random.randint(100, 9999)
            qr_data = f"{target_event},{seq}"
        elif test_type < 6:
            # 連番不正 (10%): 下限未満の連番
            seq = random.randint(1, 99)
            qr_data = f"{target_event},{seq}"
        elif test_type < 7:
            # イベント名不正 (10%): 異なるイベント名
            seq = random.randint(100, 9999)
            qr_data = f"WrongEvent,{seq}"
        elif test_type < 8:
            # フォーマット不正 (10%): カンマなし
            qr_data = f"{target_event}{random.randint(100, 999)}"
        elif test_type < 9:
            # フォーマット不正 (10%): 数値でない連番
            qr_data = f"{target_event},abc"
        else:
            # 重複データ (10%): 以前のデータを再利用（再入場テスト）
            seq = 100 + (i % 50)  # 50パターンの重複
            qr_data = f"{target_event},{seq}"

        # バリデーション実行
        result = validate_qr(qr_data, target_event, min_seq, check_event, check_seq)

        # 結果集計
        status = result.get("status", "ERROR")
        results[status] = results.get(status, 0) + 1

        # NG理由の集計
        if status == "NG":
            reason = result.get("msg", "Unknown")
            # 理由を短縮して集計
            if "イベント不一致" in reason:
                key = "イベント不一致"
            elif "無効な連番" in reason:
                key = "無効な連番"
            elif "フォーマット不正" in reason:
                key = "フォーマット不正"
            elif "使用済み" in reason:
                key = "使用済みチケット"
            else:
                key = reason
            ng_reasons[key] = ng_reasons.get(key, 0) + 1

        # 進捗表示（100件ごと）
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            print(f"  進捗: {i + 1}/{num_tests} 件 ({elapsed:.2f}秒)")

    end_time = time.time()
    total_time = end_time - start_time

    # 結果表示
    print("")
    print("=" * 60)
    print("テスト完了!")
    print("=" * 60)
    print("")
    print("【実行結果サマリー】")
    print(f"  総テスト数: {num_tests}件")
    print(f"  実行時間: {total_time:.2f}秒")
    print(f"  スループット: {num_tests / total_time:.1f}件/秒")

    print("")
    print("【判定結果】")
    for status, count in results.items():
        percentage = (count / num_tests) * 100
        bar = "#" * int(percentage / 2)
        print(f"  {status:6}: {count:5}件 ({percentage:5.1f}%) {bar}")

    if ng_reasons:
        print("")
        print("【NG理由の内訳】")
        for reason, count in sorted(ng_reasons.items(), key=lambda x: -x[1]):
            print(f"  - {reason}: {count}件")

    print("")
    print("=" * 60)

    return results

if __name__ == "__main__":
    # コマンドライン引数でテスト件数を指定可能
    num_tests = 1000
    if len(sys.argv) > 1:
        try:
            num_tests = int(sys.argv[1])
        except ValueError:
            pass

    run_tests(num_tests)

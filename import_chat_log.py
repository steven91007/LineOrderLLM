#!/usr/bin/env python
"""
把 LINE 聊天紀錄匯入 Google 表單回覆試算表

用法：
    # 只預覽，不寫入（預設）
    python import_chat_log.py chat.txt

    # 確認沒問題後才真的寫入
    python import_chat_log.py chat.txt --write

    # 連同「需人工確認」的訂單一起寫入
    python import_chat_log.py chat.txt --write --include-review
"""

import argparse
import io
import sys
from pathlib import Path

import config
from src.services.chat_log_importer import ChatLogImporter

# Windows 主控台預設 cp950，直接印中文會炸掉
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

STATUS_LABEL = {
    'ready': '可寫入',
    'review': '需確認',
    'duplicate': '已存在',
}


def main():
    parser = argparse.ArgumentParser(description='把聊天紀錄解析成訂單並寫入 Google 試算表')
    parser.add_argument('chat_log', help='聊天紀錄檔案路徑（LINE 匯出的 .txt）')
    parser.add_argument('--write', action='store_true',
                        help='實際寫入試算表；未指定時只顯示預覽')
    parser.add_argument('--include-review', action='store_true',
                        help='連同需人工確認的訂單一併寫入')
    parser.add_argument('--model', default=config.DSPY_MODEL,
                        help=f'使用的 OpenAI 模型（預設 {config.DSPY_MODEL}）')
    parser.add_argument('--no-normalize-address', action='store_true',
                        help='不要套用地址標準化，保留客人原本的寫法')
    args = parser.parse_args()

    chat_path = Path(args.chat_log)
    if not chat_path.exists():
        print(f'❌ 找不到檔案：{chat_path}')
        return 1

    missing = _check_config()
    if missing:
        print('❌ 設定不完整，缺少：' + '、'.join(missing))
        return 1

    chat_log = chat_path.read_text(encoding='utf-8')
    print(f'📄 讀取 {chat_path.name}（{len(chat_log)} 字元）')
    print(f'🤖 使用模型：{args.model}\n')

    importer = ChatLogImporter(
        api_key=config.DSPY_API_KEY,
        sheet_id=config.GOOGLE_SHEET_ID,
        credentials_path=config.GOOGLE_CREDENTIALS_PATH,
        model=args.model,
        normalize_addresses=not args.no_normalize_address,
    )

    parsed_orders = importer.parse(chat_log)
    if not parsed_orders:
        print('這段對話裡沒有解析出任何訂單。')
        return 0

    _print_preview(parsed_orders)

    if not args.write:
        ready = sum(1 for p in parsed_orders if p.status == 'ready')
        print(f'\n這是預覽，沒有寫入任何資料。確認無誤後加上 --write 就會寫入 {ready} 筆。')
        return 0

    result = importer.write(parsed_orders, include_review=args.include_review)
    if not result.get('success'):
        print(f'\n❌ 寫入失敗：{result.get("error")}')
        for mismatch in result.get('mismatches', []):
            print(f'   - {mismatch}')
        return 1

    print(f'\n✅ 已寫入 {result["appended_rows"]} 筆，略過 {result["skipped"]} 筆')
    if result.get('updated_range'):
        print(f'   範圍：{result["updated_range"]}')
    return 0


def _check_config():
    missing = []
    if not config.DSPY_API_KEY:
        missing.append('OPENAI_API_KEY')
    if not config.GOOGLE_SHEET_ID:
        missing.append('GOOGLE_SHEETS_ID')
    if not config.GOOGLE_CREDENTIALS_PATH:
        missing.append('GOOGLE_SHEETS_CREDENTIALS_PATH')
    return missing


def _print_preview(parsed_orders):
    counts = {'ready': 0, 'review': 0, 'duplicate': 0}
    for index, parsed in enumerate(parsed_orders, start=1):
        counts[parsed.status] += 1
        order = parsed.order
        items = ' / '.join(x for x in (order['giftbox'], order['family']) if x) or '（無）'

        print(f'─── 訂單 {index}　[{STATUS_LABEL[parsed.status]}] ' + '─' * 30)
        print(f'  訂購人　　：{order["orderer"] or "—"}')
        print(f'  寄件人　　：{order["sender_name"] or "—"}　{order["sender_phone"]}')
        print(f'  收件人　　：{order["receiver_name"] or "—"}　{order["receiver_phone"]}')
        print(f'  收件地址　：{order["receiver_address"] or "—"}')
        print(f'  品項　　　：{items}')
        print(f'  末五碼　　：{order["last5"] or "—"}')
        print(f'  配送日　　：{order["shipping_date"] or "—"}')
        if order['source_quote']:
            print(f'  依據　　　：{order["source_quote"]}')
        for problem in parsed.problems:
            print(f'  ⚠️  {problem}')
        if parsed.duplicate:
            print('  ⚠️  試算表中已有相同收件人／電話／配送日的訂單')
        print()

    print(f'合計 {len(parsed_orders)} 筆：'
          f'可寫入 {counts["ready"]}、需確認 {counts["review"]}、已存在 {counts["duplicate"]}')


if __name__ == '__main__':
    sys.exit(main())

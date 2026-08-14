#!/usr/bin/env python
"""
把訂單總表依「欲配送日期」拆成一天一個分頁

同一個試算表檔案裡，每個配送日期會有一個以日期命名的分頁（例如 2026-08-16），
沒填日期或日期看不懂的訂單會集中在「未指定日期」分頁。

用法：
    # 只預覽會怎麼分，不動試算表（預設）
    python organize_by_date.py

    # 確認沒問題後才真的寫入
    python organize_by_date.py --write

    # 指定來源分頁（預設「表單回覆 1」）
    python organize_by_date.py --write --source '表單回覆 1'

注意：日期分頁每次執行都會整個重建，請不要手動編輯，要改請改總表。
"""

import argparse
import io
import sys

import config
from src.services.sheet_date_organizer import SheetDateOrganizer, UNDATED_SHEET_NAME

# Windows 主控台預設 cp950，直接印中文會炸掉
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def main():
    parser = argparse.ArgumentParser(description='把訂單總表依配送日期分成不同分頁')
    parser.add_argument('--write', action='store_true',
                        help='實際寫入試算表；未指定時只顯示預覽')
    parser.add_argument('--source', default=None,
                        help='來源分頁名稱（預設「表單回覆 1」）')
    args = parser.parse_args()

    missing = _check_config()
    if missing:
        print('❌ 設定不完整，缺少：' + '、'.join(missing))
        return 1

    organizer = SheetDateOrganizer(
        credentials_path=config.GOOGLE_CREDENTIALS_PATH,
        sheet_id=config.GOOGLE_SHEET_ID,
        source_sheet=args.source,
    )

    print(f'📄 來源分頁：{organizer.source_sheet}')
    result = organizer.organize(dry_run=not args.write)

    if not result['success']:
        print(f'❌ {result["error"]}')
        return 1

    groups = result.get('groups') or {}
    if not groups:
        print(result.get('message', '沒有可分類的訂單'))
        return 0

    print(f'\n共 {result["total_rows"]} 筆訂單，分成 {len(groups)} 個分頁：')
    for sheet_name, rows in groups.items():
        mark = '⚠️ ' if sheet_name == UNDATED_SHEET_NAME else '  '
        print(f'{mark}{sheet_name}　{len(rows)} 筆')

    if not args.write:
        print('\n這是預覽，沒有寫入任何資料。確認無誤後加上 --write 就會建立／更新這些分頁。')
        return 0

    print(f'\n✅ 已寫入 {len(result["written_sheets"])} 個分頁')
    return 0


def _check_config():
    missing = []
    if not config.GOOGLE_SHEET_ID:
        missing.append('GOOGLE_SHEETS_ID')
    if not config.GOOGLE_CREDENTIALS_PATH:
        missing.append('GOOGLE_SHEETS_CREDENTIALS_PATH')
    return missing


if __name__ == '__main__':
    sys.exit(main())

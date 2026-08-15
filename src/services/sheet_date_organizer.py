"""
把訂單總表（『表單回覆 1』）依「欲配送日期」拆成一天一個分頁

同一個試算表檔案裡，每個配送日期開一個以日期命名的分頁（例如 `2026-08-16`），
內容是總表中該日期的所有訂單列，欄位順序與總表完全一致。

每個日期分頁的訂單列下方，會再附上該日的出貨統計（備貨清單），
形如 `20A 禮盒 一盒*2個地址`，統計邏輯見 shipping_summary.py。

設計上刻意做成「每次執行都重建日期分頁」：
先清空該分頁再整批寫入，所以重複執行不會產生重複資料，
總表改過之後再跑一次就會同步。也因此**不要手動編輯日期分頁**，
要改請改總表，日期分頁純粹是總表的投影。
"""

import logging
import re
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError

from ..utils.form_options import FORM_COLUMNS, FORM_RANGE
from ..utils.form_sheet_client import FormSheetClient
from .shipping_summary import summarize, summary_rows

logger = logging.getLogger(__name__)

# 配送日期在 L 欄
SHIPPING_DATE_INDEX = 11

# 沒填配送日期、或日期格式看不懂的訂單放這裡，避免資料在拆分時消失
UNDATED_SHEET_NAME = '未指定日期'

# 分頁名稱樣式：YYYY-MM-DD，用來判斷哪些分頁是本工具產生的
DATE_SHEET_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')

# 表單日期欄可能出現的寫法
_DATE_FORMATS = ('%Y/%m/%d', '%Y-%m-%d', '%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M:%S')


class SheetDateOrganizer:
    """依配送日期把總表分頁化"""

    def __init__(self, credentials_path: str, sheet_id: str,
                 source_sheet: str = None):
        self.client = FormSheetClient(
            credentials_path, sheet_id,
            **({'sheet_name': source_sheet} if source_sheet else {})
        )
        self.service = self.client.service
        self.sheet_id = sheet_id
        self.source_sheet = self.client.sheet_name

    def organize(self, dry_run: bool = True) -> Dict[str, Any]:
        """讀總表、依日期分組，並（在 dry_run=False 時）寫回各日期分頁

        Args:
            dry_run: True 只回報將會怎麼分，不動試算表

        Returns:
            分組結果與寫入狀況
        """
        try:
            rows = self.client.read_all_rows()
        except HttpError as error:
            return {'success': False, 'error': f'讀取總表失敗：{error}'}

        if len(rows) <= 1:
            return {
                'success': True,
                'groups': OrderedDict(),
                'total_rows': 0,
                'written_sheets': [],
                'message': '總表沒有訂單資料',
            }

        header = rows[0]
        groups = self._group_by_date(rows[1:])
        summaries = OrderedDict(
            (sheet_name, summarize(data_rows))
            for sheet_name, data_rows in groups.items()
        )

        try:
            existing = self._existing_sheet_names()
        except HttpError as error:
            return {'success': False, 'error': f'讀取分頁清單失敗：{error}'}

        # 訂單改了配送日期之後，原本那天的分頁會變成沒有來源的殘留資料。
        # 日期分頁是總表的投影，留著就是錯的，所以要一併清空。
        stale = [name for name in existing
                 if is_date_sheet(name) and name not in groups]

        result = {
            'success': True,
            'source_sheet': self.source_sheet,
            'groups': groups,
            'summaries': summaries,
            'total_rows': sum(len(v) for v in groups.values()),
            'written_sheets': [],
            'stale_sheets': stale,
            'dry_run': dry_run,
        }

        if dry_run:
            return result

        try:
            for sheet_name in stale:
                self._clear_sheet(sheet_name)
                logger.info(f'清空已無訂單的日期分頁：{sheet_name}')

            for sheet_name, data_rows in groups.items():
                if sheet_name not in existing:
                    self._create_sheet(sheet_name)
                self._replace_sheet_content(
                    sheet_name, header, data_rows,
                    summary_rows(summaries[sheet_name], sheet_name),
                )
                result['written_sheets'].append(sheet_name)
        except HttpError as error:
            result['success'] = False
            result['error'] = f'寫入日期分頁失敗：{error}'

        return result

    def _group_by_date(self, data_rows: List[List[Any]]) -> "OrderedDict[str, List[List[Any]]]":
        """依配送日期分組，日期由早到晚，未指定日期排最後"""
        groups: Dict[str, List[List[Any]]] = {}

        for row in data_rows:
            if not any(str(cell).strip() for cell in row):
                continue  # 略過空白列

            raw_date = row[SHIPPING_DATE_INDEX] if len(row) > SHIPPING_DATE_INDEX else ''
            sheet_name = normalize_sheet_date(raw_date) or UNDATED_SHEET_NAME
            groups.setdefault(sheet_name, []).append(row)

        # 未指定日期固定排在最後
        ordered = OrderedDict()
        for name in sorted(k for k in groups if k != UNDATED_SHEET_NAME):
            ordered[name] = groups[name]
        if UNDATED_SHEET_NAME in groups:
            ordered[UNDATED_SHEET_NAME] = groups[UNDATED_SHEET_NAME]
        return ordered

    def _existing_sheet_names(self) -> List[str]:
        spreadsheet = self.service.spreadsheets().get(spreadsheetId=self.sheet_id).execute()
        return [s['properties']['title'] for s in spreadsheet.get('sheets', [])]

    def _create_sheet(self, sheet_name: str) -> None:
        """新增分頁並凍結標題列"""
        response = self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.sheet_id,
            body={'requests': [{
                'addSheet': {
                    'properties': {
                        'title': sheet_name,
                        'gridProperties': {'frozenRowCount': 1},
                    }
                }
            }]},
        ).execute()

        new_sheet_id = (response['replies'][0]['addSheet']['properties']['sheetId'])
        # 標題列加粗、灰底，和總表的視覺一致
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.sheet_id,
            body={'requests': [{
                'repeatCell': {
                    'range': {'sheetId': new_sheet_id, 'startRowIndex': 0, 'endRowIndex': 1},
                    'cell': {
                        'userEnteredFormat': {
                            'textFormat': {'bold': True},
                            'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
                        }
                    },
                    'fields': 'userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor',
                }
            }]},
        ).execute()
        logger.info(f'建立日期分頁：{sheet_name}')

    def _clear_sheet(self, sheet_name: str) -> None:
        """清空分頁內容（統計區塊只佔 A 欄，清除範圍仍用 A:L 蓋掉整片舊內容）"""
        self.service.spreadsheets().values().clear(
            spreadsheetId=self.sheet_id,
            range=f"'{sheet_name}'!{FORM_RANGE}",
            body={},
        ).execute()

    def _replace_sheet_content(self, sheet_name: str, header: List[Any],
                               data_rows: List[List[Any]],
                               extra_rows: List[List[Any]] = None) -> None:
        """清空分頁後重新寫入標題列、訂單列，以及附在下方的統計區塊"""
        self._clear_sheet(sheet_name)

        # 用 RAW 而不是 USER_ENTERED：總表讀出來的已經是顯示值，
        # 交給 Sheets 重新解讀會把電話 0937... 當成數字吃掉開頭的 0。
        self.service.spreadsheets().values().update(
            spreadsheetId=self.sheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption='RAW',
            body={'values': [header] + data_rows + (extra_rows or []),
                  'majorDimension': 'ROWS'},
        ).execute()


def normalize_sheet_date(value: Any) -> Optional[str]:
    """把配送日期欄的值轉成分頁名稱 `YYYY-MM-DD`，看不懂就回 None"""
    text = str(value or '').strip()
    if not text:
        return None

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue

    # 「2026/8/16(星期日)」這種帶註記的寫法，先把括號拿掉再試一次
    stripped = re.split(r'[（(]', text)[0].strip()
    if stripped and stripped != text:
        return normalize_sheet_date(stripped)

    return None


def is_date_sheet(sheet_name: str) -> bool:
    """判斷分頁是否為本工具產生的日期分頁"""
    return bool(DATE_SHEET_PATTERN.match(sheet_name)) or sheet_name == UNDATED_SHEET_NAME


__all__ = [
    'SheetDateOrganizer',
    'normalize_sheet_date',
    'is_date_sheet',
    'UNDATED_SHEET_NAME',
    'FORM_COLUMNS',
]

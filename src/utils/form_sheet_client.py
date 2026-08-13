"""
Google 表單回覆試算表的寫入客戶端

GoogleSheetsClient 寫的是舊的 10 欄自訂格式，而且會依出貨日自動開新分頁；
表單回覆試算表是固定的 12 欄單一分頁，兩者不相容，所以獨立成這個類別。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .form_options import FORM_COLUMNS, FORM_RANGE

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
DEFAULT_SHEET_NAME = '表單回覆 1'


class FormSheetClient:
    """讀寫『表單回覆 1』分頁"""

    def __init__(self, credentials_path: str, sheet_id: str,
                 sheet_name: str = DEFAULT_SHEET_NAME):
        self.credentials_path = credentials_path
        self.sheet_id = sheet_id
        self.sheet_name = sheet_name
        self.service = self._build_service()

    def _build_service(self):
        credentials = Credentials.from_service_account_file(
            self.credentials_path, scopes=SCOPES
        )
        return build('sheets', 'v4', credentials=credentials)

    def _range(self, cells: str) -> str:
        # 分頁名稱含空白，一定要加單引號
        return f"'{self.sheet_name}'!{cells}"

    def verify_columns(self) -> Dict[str, Any]:
        """確認試算表的欄位順序和程式預期的一致

        表單改題目會讓欄位位移，寫入就會錯位，所以每次寫入前都先驗一次。
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=self._range('A1:L1'),
            ).execute()
        except HttpError as error:
            return {'ok': False, 'error': f'讀取標題列失敗：{error}'}

        actual = result.get('values', [[]])
        actual = actual[0] if actual else []

        if actual == FORM_COLUMNS:
            return {'ok': True, 'columns': actual}

        mismatches = []
        for index, expected in enumerate(FORM_COLUMNS):
            found = actual[index] if index < len(actual) else '<缺少>'
            if found != expected:
                column_letter = chr(ord('A') + index)
                mismatches.append(f'{column_letter} 欄：預期「{expected}」，實際「{found}」')

        return {
            'ok': False,
            'error': '試算表欄位與程式預期不符，表單題目可能被改過',
            'mismatches': mismatches,
            'columns': actual,
        }

    def existing_keys(self) -> set:
        """回傳已存在訂單的識別鍵，用來避免重複寫入

        識別鍵取「收件人 + 收件人電話 + 配送日期」，這三者相同幾乎可以確定是同一筆。
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=self._range(FORM_RANGE),
                valueRenderOption='FORMATTED_VALUE',
            ).execute()
        except HttpError as error:
            logger.warning(f'讀取既有訂單失敗，略過重複檢查：{error}')
            return set()

        rows = result.get('values', [])[1:]  # 跳過標題列
        keys = set()
        for row in rows:
            padded = row + [''] * (12 - len(row))
            keys.add(dedup_key(padded[5], padded[6], padded[11]))
        return keys

    def append_rows(self, rows: List[List[Any]]) -> Dict[str, Any]:
        """把資料列附加到分頁最後"""
        if not rows:
            return {'success': True, 'appended_rows': 0}

        try:
            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=self._range(FORM_RANGE),
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': rows, 'majorDimension': 'ROWS'},
            ).execute()
        except HttpError as error:
            return {'success': False, 'error': f'Google Sheets API 錯誤：{error}'}

        updates = result.get('updates', {})
        return {
            'success': True,
            'appended_rows': updates.get('updatedRows', 0),
            'updated_range': updates.get('updatedRange', ''),
        }


def dedup_key(receiver_name: str, receiver_phone: str, shipping_date: str) -> str:
    """產生訂單識別鍵，電話去掉分隔符號、日期正規化，避免格式差異造成漏判"""
    phone = ''.join(ch for ch in (receiver_phone or '') if ch.isdigit())
    date = _normalize_date(shipping_date)
    return f'{(receiver_name or "").strip()}|{phone}|{date}'


def _normalize_date(value: str) -> str:
    """把 2026/8/16、2026-08-16 等寫法統一成 2026-08-16"""
    text = (value or '').strip()
    if not text:
        return ''
    for fmt in ('%Y/%m/%d', '%Y-%m-%d', '%Y/%m/%d %H:%M:%S'):
        try:
            return datetime.strptime(text, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return text


def format_timestamp(moment: datetime) -> str:
    """輸出成表單時間戳記的樣子（USER_ENTERED 會轉成真正的日期時間值）"""
    return moment.strftime('%Y/%m/%d %H:%M:%S')


def format_shipping_date(value: Optional[str]) -> str:
    """配送日期欄存的是真正的日期值，寫入 YYYY/M/D 讓 Sheets 自動轉型"""
    normalized = _normalize_date(value or '')
    if not normalized:
        return ''
    try:
        parsed = datetime.strptime(normalized, '%Y-%m-%d')
    except ValueError:
        return normalized
    return f'{parsed.year}/{parsed.month}/{parsed.day}'

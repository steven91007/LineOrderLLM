"""
Write client for the Google Form responses spreadsheet.

GoogleSheetsClient writes the old custom 10-column format and automatically
opens a new tab per shipping date; the form responses spreadsheet is a single
fixed 12-column tab. The two are incompatible, hence this separate class.
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
    """Read and write the 『表單回覆 1』 (form responses 1) tab."""

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
        # The tab name contains a space, so it must be single-quoted
        return f"'{self.sheet_name}'!{cells}"

    def verify_columns(self) -> Dict[str, Any]:
        """Confirm the spreadsheet's column order matches what the code expects.

        Editing the form's questions shifts the columns and would misalign
        writes, so this is checked before every write.
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=self._range('A1:L1'),
            ).execute()
        except HttpError as error:
            return {'ok': False, 'error': f'讀取標題列失敗：{error}'}  # shown in Discord/GUI ("failed to read header row")

        actual = result.get('values', [[]])
        actual = actual[0] if actual else []

        if actual == FORM_COLUMNS:
            return {'ok': True, 'columns': actual}

        mismatches = []
        for index, expected in enumerate(FORM_COLUMNS):
            found = actual[index] if index < len(actual) else '<缺少>'
            if found != expected:
                column_letter = chr(ord('A') + index)
                # Shown in Discord/GUI: "column X: expected ..., actual ..."
                mismatches.append(f'{column_letter} 欄：預期「{expected}」，實際「{found}」')

        return {
            'ok': False,
            'error': '試算表欄位與程式預期不符，表單題目可能被改過',  # shown in Discord/GUI
            'mismatches': mismatches,
            'columns': actual,
        }

    def existing_keys(self) -> set:
        """Return the identity keys of existing orders, used to avoid duplicate writes.

        The key is receiver + receiver phone + delivery date; when all three
        match it is almost certainly the same order.
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=self._range(FORM_RANGE),
                valueRenderOption='FORMATTED_VALUE',
            ).execute()
        except HttpError as error:
            logger.warning(f'Failed to read existing orders, skipping duplicate check: {error}')
            return set()

        rows = result.get('values', [])[1:]  # Skip the header row
        keys = set()
        for row in rows:
            padded = row + [''] * (12 - len(row))
            keys.add(dedup_key(padded[5], padded[6], padded[11]))
        return keys

    def read_all_rows(self) -> List[List[Any]]:
        """Read the whole tab (including the header row), padding each row to 12 columns."""
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.sheet_id,
            range=self._range(FORM_RANGE),
            valueRenderOption='FORMATTED_VALUE',
        ).execute()

        rows = result.get('values', [])
        return [row + [''] * (len(FORM_COLUMNS) - len(row)) for row in rows]

    def append_rows(self, rows: List[List[Any]]) -> Dict[str, Any]:
        """Append data rows to the end of the tab."""
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
            return {'success': False, 'error': f'Google Sheets API 錯誤：{error}'}  # shown in Discord/GUI

        updates = result.get('updates', {})
        return {
            'success': True,
            'appended_rows': updates.get('updatedRows', 0),
            'updated_range': updates.get('updatedRange', ''),
        }


def dedup_key(receiver_name: str, receiver_phone: str, shipping_date: str) -> str:
    """Build the order identity key; strip separators from the phone and normalize the date so formatting differences don't cause missed matches."""
    phone = ''.join(ch for ch in (receiver_phone or '') if ch.isdigit())
    date = _normalize_date(shipping_date)
    return f'{(receiver_name or "").strip()}|{phone}|{date}'


def _normalize_date(value: str) -> str:
    """Normalize forms like 2026/8/16 and 2026-08-16 to 2026-08-16."""
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
    """Format like a form timestamp (USER_ENTERED converts it to a real datetime value)."""
    return moment.strftime('%Y/%m/%d %H:%M:%S')


def format_shipping_date(value: Optional[str]) -> str:
    """The delivery date column holds real date values; write YYYY/M/D so Sheets converts it automatically."""
    normalized = _normalize_date(value or '')
    if not normalized:
        return ''
    try:
        parsed = datetime.strptime(normalized, '%Y-%m-%d')
    except ValueError:
        return normalized
    return f'{parsed.year}/{parsed.month}/{parsed.day}'

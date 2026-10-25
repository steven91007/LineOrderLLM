"""
Split the master order sheet (『表單回覆 1』) by "欲配送日期" (desired delivery
date) into one tab per day.

Within the same spreadsheet file, each delivery date gets a tab named after the
date (e.g. `2026-08-16`) holding all of the master sheet's order rows for that
date, with exactly the same column order as the master sheet.

Below each date tab's order rows, that day's shipping statistics (packing list)
are appended, e.g. `20A 禮盒 1盒*2個地址`; see shipping_summary.py for the logic.

Order rows get alternating background colors (light orange on even rows) so
elderly staff can read across a row without drifting onto the next one.

By design, date tabs are rebuilt on every run: the tab is cleared and then
written in one batch, so repeated runs never create duplicate data, and
re-running after the master sheet changes brings them back in sync. For the
same reason, **do not edit date tabs by hand** -- make changes in the master
sheet; date tabs are purely a projection of it.
"""

import logging
import re
from collections import OrderedDict
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError

from ..utils.form_options import FORM_COLUMNS, FORM_RANGE
from ..utils.form_sheet_client import FormSheetClient
from .shipping_summary import summarize, summary_rows

logger = logging.getLogger(__name__)

# The delivery date is in column L
SHIPPING_DATE_INDEX = 11

# Orders with no delivery date, or an unreadable one, go here so no data is lost during the split
UNDATED_SHEET_NAME = '未指定日期'

# Tab name pattern YYYY-MM-DD, used to tell which tabs this tool generated
DATE_SHEET_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')

# Formats that may appear in the form date column
_DATE_FORMATS = ('%Y/%m/%d', '%Y-%m-%d', '%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M:%S')

# Alternating row colors for order rows: even rows (2, 4, 6, ...) light orange, odd rows white.
# Elderly staff easily skip lines when reading long rows of text; banding keeps the eye on one row.
# The low-saturation light orange (#FFE0B2) is deliberate so black text stays legible when printed or projected.
BAND_COLOR = {'red': 1.0, 'green': 0.878, 'blue': 0.698}
BAND_ALT_COLOR = {'red': 1.0, 'green': 1.0, 'blue': 1.0}


class SheetDateOrganizer:
    """Split the master sheet into tabs by delivery date."""

    def __init__(self, credentials_path: str, sheet_id: str,
                 source_sheet: str = None):
        self.client = FormSheetClient(
            credentials_path, sheet_id,
            **({'sheet_name': source_sheet} if source_sheet else {})
        )
        self.service = self.client.service
        self.sheet_id = sheet_id
        self.source_sheet = self.client.sheet_name

    def organize(self, dry_run: bool = True,
                 today: Optional[date] = None) -> Dict[str, Any]:
        """Read the master sheet, group by date, and (when dry_run=False) write back each date tab.

        Args:
            dry_run: If True, only report how rows would be split without touching the spreadsheet

        Returns:
            The grouping result and write status
        """
        try:
            rows = self.client.read_all_rows()
        except HttpError as error:
            return {'success': False, 'error': f'讀取總表失敗：{error}'}  # shown in Discord

        if len(rows) <= 1:
            return {
                'success': True,
                'groups': OrderedDict(),
                'total_rows': 0,
                'written_sheets': [],
                'message': '總表沒有訂單資料',  # shown in Discord ("master sheet has no orders")
            }

        header = rows[0]
        groups = self._group_by_date(rows[1:])
        summaries = OrderedDict(
            (sheet_name, summarize(data_rows))
            for sheet_name, data_rows in groups.items()
        )

        try:
            existing = self._existing_sheets()
        except HttpError as error:
            return {'success': False, 'error': f'讀取分頁清單失敗：{error}'}  # shown in Discord

        # Tabs whose shipping date has passed are locked: the goods have shipped, so that list is a
        # historical record and should no longer follow the master sheet. Even if someone later edits
        # an old order in the master sheet, it won't overwrite what the list looked like at shipping time.
        today = today or date.today()
        locked = [name for name in groups if is_past_sheet(name, today)]

        # When an order's delivery date changes, the original day's tab is left with orphaned data.
        # Date tabs are a projection of the master sheet, so keeping it would be wrong; clear it too.
        # Already-shipped tabs don't count as stale -- they aren't supposed to have matching orders anymore.
        stale = [name for name in existing
                 if is_date_sheet(name) and name not in groups
                 and not is_past_sheet(name, today)]

        result = {
            'success': True,
            'source_sheet': self.source_sheet,
            'groups': groups,
            'summaries': summaries,
            'total_rows': sum(len(v) for v in groups.values()),
            'written_sheets': [],
            'stale_sheets': stale,
            'locked_sheets': locked,
            'dry_run': dry_run,
        }

        if dry_run:
            return result

        try:
            for sheet_name in stale:
                self._clear_sheet(sheet_name)
                self._apply_banding(existing[sheet_name], 0)
                logger.info(f'Cleared date tab with no remaining orders: {sheet_name}')

            for sheet_name, data_rows in groups.items():
                meta = existing.get(sheet_name) or self._create_sheet(sheet_name)

                if sheet_name in locked:
                    # Already shipped: leave the content as-is, just make sure the protection is still there
                    self._protect_sheet(sheet_name, meta)
                    continue

                self._replace_sheet_content(
                    sheet_name, header, data_rows,
                    summary_rows(summaries[sheet_name], sheet_name),
                )
                self._apply_banding(meta, len(data_rows))
                result['written_sheets'].append(sheet_name)
        except HttpError as error:
            result['success'] = False
            result['error'] = f'寫入日期分頁失敗：{error}'  # shown in Discord

        return result

    def _group_by_date(self, data_rows: List[List[Any]]) -> "OrderedDict[str, List[List[Any]]]":
        """Group by delivery date, earliest first, with the unspecified-date group last."""
        groups: Dict[str, List[List[Any]]] = {}

        for row in data_rows:
            if not any(str(cell).strip() for cell in row):
                continue  # Skip blank rows

            raw_date = row[SHIPPING_DATE_INDEX] if len(row) > SHIPPING_DATE_INDEX else ''
            sheet_name = normalize_sheet_date(raw_date) or UNDATED_SHEET_NAME
            groups.setdefault(sheet_name, []).append(row)

        # The unspecified-date group always goes last
        ordered = OrderedDict()
        for name in sorted(k for k in groups if k != UNDATED_SHEET_NAME):
            ordered[name] = groups[name]
        if UNDATED_SHEET_NAME in groups:
            ordered[UNDATED_SHEET_NAME] = groups[UNDATED_SHEET_NAME]
        return ordered

    def _existing_sheets(self) -> "OrderedDict[str, Dict[str, Any]]":
        """Tab name -> {'id': tab gid, 'bandings': ids of existing row bandings}

        To re-apply banding we need the old banding ids so they can be deleted
        first, so bandedRanges is read back here as well to save an extra API call.
        """
        spreadsheet = self.service.spreadsheets().get(
            spreadsheetId=self.sheet_id,
            fields=('sheets(properties(sheetId,title),bandedRanges(bandedRangeId),'
                    'protectedRanges(protectedRangeId,description))'),
        ).execute()

        sheets = OrderedDict()
        for sheet in spreadsheet.get('sheets', []):
            props = sheet['properties']
            sheets[props['title']] = {
                'id': props['sheetId'],
                'bandings': [b['bandedRangeId'] for b in sheet.get('bandedRanges', [])],
                'protections': [r['protectedRangeId'] for r in sheet.get('protectedRanges', [])],
            }
        return sheets

    def _create_sheet(self, sheet_name: str) -> Dict[str, Any]:
        """Add a tab and freeze the header row; returns {'id', 'bandings'}."""
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
        # Bold header row with gray background, matching the master sheet
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
        logger.info(f'Created date tab: {sheet_name}')
        return {'id': new_sheet_id, 'bandings': []}

    def _apply_banding(self, meta: Dict[str, Any], data_row_count: int) -> None:
        """Reset the alternating row colors of the order rows (light orange on even rows).

        Tabs are rebuilt every time and the row count changes, so the old banding
        is deleted first and rebuilt for this run's row count; otherwise the old
        range could cover the packing list below, or leave an empty orange strip
        after the number of orders shrinks.

        Args:
            meta: The {'id', 'bandings'} from `_existing_sheets` / `_create_sheet`
            data_row_count: Number of order rows (excluding the header); 0 means delete only, add nothing
        """
        requests = [{'deleteBanding': {'bandedRangeId': banding_id}}
                    for banding_id in meta.get('bandings', [])]

        if data_row_count > 0:
            # The range starts at row 2 (after the header), so the first band lands on sheet row 2
            # and then every other row -> the light orange falls exactly on even rows.
            requests.append({'addBanding': {'bandedRange': {
                'range': {
                    'sheetId': meta['id'],
                    'startRowIndex': 1,
                    'endRowIndex': 1 + data_row_count,
                    'startColumnIndex': 0,
                    'endColumnIndex': len(FORM_COLUMNS),
                },
                'rowProperties': {
                    'firstBandColor': BAND_COLOR,
                    'secondBandColor': BAND_ALT_COLOR,
                },
            }}})

        if not requests:
            return

        response = self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.sheet_id,
            body={'requests': requests},
        ).execute()

        # If the same tab is written again in the same run, the one to delete is the banding just added
        meta['bandings'] = [
            reply['addBanding']['bandedRange']['bandedRangeId']
            for reply in response.get('replies', []) if 'addBanding' in reply
        ]

    def _protect_sheet(self, sheet_name: str, meta: Dict[str, Any]) -> None:
        """Add protection to an already-shipped date tab.

        Uses warningOnly: when editing, Google shows a "you are editing a protected
        cell" confirmation, which guards against slips without locking anyone out
        (including the service account this program uses). Restricting editors
        instead could cost the service account its write access, which would be
        painful to undo later.
        """
        if meta.get('protections'):
            return  # Already protected; adding again would pile up overlapping protected ranges

        try:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body={'requests': [{
                    'addProtectedRange': {
                        'protectedRange': {
                            'range': {'sheetId': meta['id']},
                            'description': f'{sheet_name} 已出貨，內容鎖定',  # shown in Sheets ("shipped, content locked")
                            'warningOnly': True,
                        }
                    }
                }]},
            ).execute()
            meta.setdefault('protections', []).append(True)
            logger.info(f'Locked shipped date tab: {sheet_name}')
        except HttpError as error:
            # Failing to lock shouldn't fail the whole batch; just log it
            logger.warning(f'Failed to lock tab {sheet_name}: {error}')

    def _clear_sheet(self, sheet_name: str) -> None:
        """Clear the tab content (the statistics block only uses column A, but A:L is cleared to wipe all old content)."""
        self.service.spreadsheets().values().clear(
            spreadsheetId=self.sheet_id,
            range=f"'{sheet_name}'!{FORM_RANGE}",
            body={},
        ).execute()

    def _replace_sheet_content(self, sheet_name: str, header: List[Any],
                               data_rows: List[List[Any]],
                               extra_rows: List[List[Any]] = None) -> None:
        """Clear the tab, then rewrite the header row, order rows, and the statistics block below them."""
        self._clear_sheet(sheet_name)

        # Use RAW rather than USER_ENTERED: values read from the master sheet are already display values,
        # and letting Sheets re-interpret them would treat phone 0937... as a number and drop the leading 0.
        self.service.spreadsheets().values().update(
            spreadsheetId=self.sheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption='RAW',
            body={'values': [header] + data_rows + (extra_rows or []),
                  'majorDimension': 'ROWS'},
        ).execute()


def is_past_sheet(sheet_name: str, today: date) -> bool:
    """Whether the tab's date has already passed (today does not count)."""
    if not DATE_SHEET_PATTERN.match(sheet_name):
        return False  # Non-date tabs such as the unspecified-date tab are never locked
    return datetime.strptime(sheet_name, '%Y-%m-%d').date() < today


def normalize_sheet_date(value: Any) -> Optional[str]:
    """Convert a delivery date cell value into a tab name `YYYY-MM-DD`; return None if unreadable."""
    text = str(value or '').strip()
    if not text:
        return None

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue

    # For annotated forms like 「2026/8/16(星期日)」, strip the parenthesized part and try again
    stripped = re.split(r'[（(]', text)[0].strip()
    if stripped and stripped != text:
        return normalize_sheet_date(stripped)

    return None


def is_date_sheet(sheet_name: str) -> bool:
    """Determine whether a tab is a date tab generated by this tool."""
    return bool(DATE_SHEET_PATTERN.match(sheet_name)) or sheet_name == UNDATED_SHEET_NAME


__all__ = [
    'SheetDateOrganizer',
    'is_past_sheet',
    'normalize_sheet_date',
    'is_date_sheet',
    'UNDATED_SHEET_NAME',
    'FORM_COLUMNS',
]

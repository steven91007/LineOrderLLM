"""Find orders whose shipping date is wrong.

CONTEXT.md: only Wednesday and Sunday are shipping days. The form's date is a
dropdown, but the master sheet may have been edited by hand, or early data was
already off, so we need a tool that can audit the whole master sheet at any time.

Reported in three categories:
    offday    A date is filled in, but that day is not a shipping day (wrong day)
    unknown   The date cell is blank or unreadable (worse, since it can't be placed in a date tab)
    backdated The shipping date is earlier than the submission time -- the date was
              already in the past when the form was filled, so it must be a mistake

This is read-only; running it any number of times never touches the spreadsheet.
"""

import logging
from collections import OrderedDict
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError

from ..utils.form_options import FORM_COLUMNS
from ..utils.form_sheet_client import FormSheetClient
from ..utils.shipping_days import is_shipping_day, weekday_name
from .sheet_date_organizer import SHIPPING_DATE_INDEX, normalize_sheet_date

logger = logging.getLogger(__name__)

# Columns shown in the report (indexes into FORM_COLUMNS)
TIMESTAMP_INDEX = 0
ORDERER_INDEX = 1
RECEIVER_NAME_INDEX = 5
RECEIVER_PHONE_INDEX = 6
GIFTBOX_INDEX = 8
FAMILY_INDEX = 9

# Formats the form timestamp may take (format_timestamp writes the first one)
_TIMESTAMP_FORMATS = ('%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M:%S',
                      '%Y/%m/%d %H:%M', '%Y-%m-%d %H:%M')


class OffdayOrder:
    """An order with a problematic shipping date."""

    __slots__ = ('row_number', 'raw_date', 'shipping_date', 'orderer',
                 'receiver_name', 'receiver_phone', 'items', 'submitted_at')

    def __init__(self, row_number: int, raw_date: str, shipping_date: Optional[str],
                 orderer: str, receiver_name: str, receiver_phone: str, items: str,
                 submitted_at: Optional[datetime] = None):
        self.row_number = row_number          # Actual row number on the master sheet, so you can jump straight to it to fix
        self.raw_date = raw_date              # Raw text of the date cell
        self.shipping_date = shipping_date    # YYYY-MM-DD when readable, otherwise None
        self.orderer = orderer
        self.receiver_name = receiver_name
        self.receiver_phone = receiver_phone
        self.items = items
        self.submitted_at = submitted_at   # Submission time; None when unreadable

    @property
    def weekday_label(self) -> str:
        """e.g. 「星期二」 (Tuesday); empty string when the date is unreadable."""
        if not self.shipping_date:
            return ''
        parsed = datetime.strptime(self.shipping_date, '%Y-%m-%d')
        return f'星期{weekday_name(parsed.date())}'

    @property
    def submitted_label(self) -> str:
        return self.submitted_at.strftime('%Y-%m-%d') if self.submitted_at else '—'

    def __repr__(self) -> str:
        return f'<OffdayOrder row {self.row_number} {self.raw_date} {self.receiver_name}>'


class OffdayOrderAuditor:
    """Scan the master sheet for orders whose shipping date is not a Wednesday/Sunday."""

    def __init__(self, credentials_path: str, sheet_id: str,
                 source_sheet: str = None):
        self.client = FormSheetClient(
            credentials_path, sheet_id,
            **({'sheet_name': source_sheet} if source_sheet else {})
        )
        self.sheet_id = sheet_id
        self.source_sheet = self.client.sheet_name

    def audit(self, include_past: bool = False,
              today: Optional[date] = None) -> Dict[str, Any]:
        """Scan the master sheet.

        Args:
            include_past: If True, also list shipping dates that have already passed (for stock-taking).
                          Defaults to False, listing only today onward -- past ones have shipped and can't be changed.
            today: Reference date for deciding what is "past"; defaults to today.

        Returns:
            On success:
                {'success': True, 'source_sheet': str, 'total_rows': int,
                 'offday': OrderedDict[date -> List[OffdayOrder]],
                 'unknown': List[OffdayOrder],
                 'backdated': List[OffdayOrder],
                 'offday_count': int, 'unknown_count': int, 'backdated_count': int,
                 'skipped_past': int, 'include_past': bool}
            On failure:
                {'success': False, 'error': str}

        Note that backdated is not affected by include_past. A shipping date earlier
        than the submission time is necessarily also earlier than today, so applying
        include_past would hide it by default -- but it's a data-entry error, not a
        scheduling issue, so it is always listed. The same row may appear in both
        offday and backdated; those are two different problems.
        """
        today = today or date.today()

        try:
            rows = self.client.read_all_rows()
        except HttpError as error:
            return {'success': False, 'error': f'讀取總表失敗：{error}'}  # shown in Discord

        if len(rows) <= 1:
            return {
                'success': True,
                'source_sheet': self.source_sheet,
                'total_rows': 0,
                'offday': OrderedDict(),
                'unknown': [],
                'backdated': [],
                'offday_count': 0,
                'unknown_count': 0,
                'backdated_count': 0,
                'skipped_past': 0,
                'include_past': include_past,
                'message': '總表沒有訂單資料',  # shown in Discord ("master sheet has no orders")
            }

        offday: Dict[str, List[OffdayOrder]] = {}
        unknown: List[OffdayOrder] = []
        backdated: List[OffdayOrder] = []
        total = 0
        skipped_past = 0

        # The header is row 1, so data row numbers start at 2
        for offset, row in enumerate(rows[1:], start=2):
            if not any(str(cell).strip() for cell in row):
                continue  # Skip blank rows
            total += 1

            raw_date = str(row[SHIPPING_DATE_INDEX] if len(row) > SHIPPING_DATE_INDEX else '').strip()
            normalized = normalize_sheet_date(raw_date)
            order = _build_order(offset, row, raw_date, normalized)

            if normalized is None:
                # Date blank or unreadable -- can't tell whether it's a shipping day, so always list it
                unknown.append(order)
                continue

            parsed = datetime.strptime(normalized, '%Y-%m-%d').date()

            # Shipping date earlier than submission time: the date was already past when filled in, so it's a mistake.
            # include_past is not applied -- such rows are necessarily before today and would never be seen if filtered,
            # yet this is a data-entry error, not a scheduling issue.
            if order.submitted_at and parsed < order.submitted_at.date():
                backdated.append(order)

            if is_shipping_day(parsed):
                continue

            if not include_past and parsed < today:
                skipped_past += 1
                continue

            offday.setdefault(normalized, []).append(order)

        ordered = OrderedDict((d, offday[d]) for d in sorted(offday))

        return {
            'success': True,
            'source_sheet': self.source_sheet,
            'total_rows': total,
            'offday': ordered,
            'unknown': unknown,
            'backdated': backdated,
            'offday_count': sum(len(v) for v in ordered.values()),
            'unknown_count': len(unknown),
            'backdated_count': len(backdated),
            'skipped_past': skipped_past,
            'include_past': include_past,
        }


def _build_order(row_number: int, row: List[Any], raw_date: str,
                 normalized: Optional[str]) -> OffdayOrder:
    def cell(index: int) -> str:
        return str(row[index]).strip() if len(row) > index else ''

    items = ' / '.join(x for x in (cell(GIFTBOX_INDEX), cell(FAMILY_INDEX)) if x)
    return OffdayOrder(
        submitted_at=_parse_timestamp(cell(TIMESTAMP_INDEX)),
        row_number=row_number,
        raw_date=raw_date,
        shipping_date=normalized,
        orderer=cell(ORDERER_INDEX),
        receiver_name=cell(RECEIVER_NAME_INDEX),
        receiver_phone=cell(RECEIVER_PHONE_INDEX),
        items=items or '（無）',  # "(none)", shown in Discord
    )


def _parse_timestamp(text: str) -> Optional[datetime]:
    """Parse the form timestamp in column A; return None if unreadable (that row then skips the submission-time check)."""
    if not text:
        return None
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    # For forms with Chinese text like 「2026/8/21 上午 10:00:00」, just take the date part
    head = text.split()[0] if text.split() else ''
    return normalize_sheet_date(head) and datetime.strptime(
        normalize_sheet_date(head), '%Y-%m-%d') or None


__all__ = ['OffdayOrderAuditor', 'OffdayOrder', 'FORM_COLUMNS']

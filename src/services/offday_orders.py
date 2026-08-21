"""揪出出貨日不對的訂單

CONTEXT.md：只有週三與週日是出貨日。表單的日期是下拉選項，但總表可能被手動
編輯過、或早期資料就是歪的，所以需要一支能隨時稽核整張總表的工具。

分成兩類回報：
    offday   有填日期，但那天不是出貨日（填錯日子）
    unknown  日期欄空白，或填了看不懂的東西（更麻煩，因為排不進日期分頁）

這裡只讀不寫，跑幾次都不會動到試算表。
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

# 報告裡要顯示的欄位（對應 FORM_COLUMNS 的索引）
ORDERER_INDEX = 1
RECEIVER_NAME_INDEX = 5
RECEIVER_PHONE_INDEX = 6
GIFTBOX_INDEX = 8
FAMILY_INDEX = 9


class OffdayOrder:
    """一筆出貨日有問題的訂單"""

    __slots__ = ('row_number', 'raw_date', 'shipping_date', 'orderer',
                 'receiver_name', 'receiver_phone', 'items')

    def __init__(self, row_number: int, raw_date: str, shipping_date: Optional[str],
                 orderer: str, receiver_name: str, receiver_phone: str, items: str):
        self.row_number = row_number          # 總表上的實際列號，方便直接跳過去改
        self.raw_date = raw_date              # 日期欄的原始文字
        self.shipping_date = shipping_date    # 看得懂時的 YYYY-MM-DD，否則 None
        self.orderer = orderer
        self.receiver_name = receiver_name
        self.receiver_phone = receiver_phone
        self.items = items

    @property
    def weekday_label(self) -> str:
        """「星期二」；日期看不懂時回空字串"""
        if not self.shipping_date:
            return ''
        parsed = datetime.strptime(self.shipping_date, '%Y-%m-%d')
        return f'星期{weekday_name(parsed.date())}'

    def __repr__(self) -> str:
        return f'<OffdayOrder 第{self.row_number}列 {self.raw_date} {self.receiver_name}>'


class OffdayOrderAuditor:
    """掃描總表，找出出貨日不是週三／週日的訂單"""

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
        """掃描總表

        Args:
            include_past: True 會連已經過去的出貨日一起列（盤點用）。
                          預設 False，只列今天以後的——過去的已經出貨了，改不了。
            today: 判斷「過去」的基準日，預設今天。

        Returns:
            成功時：
                {'success': True, 'source_sheet': str, 'total_rows': int,
                 'offday': OrderedDict[日期 -> List[OffdayOrder]],
                 'unknown': List[OffdayOrder],
                 'offday_count': int, 'unknown_count': int,
                 'skipped_past': int, 'include_past': bool}
            失敗時：
                {'success': False, 'error': str}
        """
        today = today or date.today()

        try:
            rows = self.client.read_all_rows()
        except HttpError as error:
            return {'success': False, 'error': f'讀取總表失敗：{error}'}

        if len(rows) <= 1:
            return {
                'success': True,
                'source_sheet': self.source_sheet,
                'total_rows': 0,
                'offday': OrderedDict(),
                'unknown': [],
                'offday_count': 0,
                'unknown_count': 0,
                'skipped_past': 0,
                'include_past': include_past,
                'message': '總表沒有訂單資料',
            }

        offday: Dict[str, List[OffdayOrder]] = {}
        unknown: List[OffdayOrder] = []
        total = 0
        skipped_past = 0

        # 標題列是第 1 列，所以資料列的列號從 2 開始
        for offset, row in enumerate(rows[1:], start=2):
            if not any(str(cell).strip() for cell in row):
                continue  # 略過空白列
            total += 1

            raw_date = str(row[SHIPPING_DATE_INDEX] if len(row) > SHIPPING_DATE_INDEX else '').strip()
            normalized = normalize_sheet_date(raw_date)
            order = _build_order(offset, row, raw_date, normalized)

            if normalized is None:
                # 日期空白或看不懂——沒辦法判斷是不是出貨日，一律列出來
                unknown.append(order)
                continue

            parsed = datetime.strptime(normalized, '%Y-%m-%d').date()
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
            'offday_count': sum(len(v) for v in ordered.values()),
            'unknown_count': len(unknown),
            'skipped_past': skipped_past,
            'include_past': include_past,
        }


def _build_order(row_number: int, row: List[Any], raw_date: str,
                 normalized: Optional[str]) -> OffdayOrder:
    def cell(index: int) -> str:
        return str(row[index]).strip() if len(row) > index else ''

    items = ' / '.join(x for x in (cell(GIFTBOX_INDEX), cell(FAMILY_INDEX)) if x)
    return OffdayOrder(
        row_number=row_number,
        raw_date=raw_date,
        shipping_date=normalized,
        orderer=cell(ORDERER_INDEX),
        receiver_name=cell(RECEIVER_NAME_INDEX),
        receiver_phone=cell(RECEIVER_PHONE_INDEX),
        items=items or '（無）',
    )


__all__ = ['OffdayOrderAuditor', 'OffdayOrder', 'FORM_COLUMNS']

# Order Collection and Consolidation (訂單收集與彙整)

Receives gift-box orders, consolidates them by date and item, and proactively delivers the details to the owner every day. Orders come from a Google Form; shipping data lives in Google Sheets.

## Language

### Orders

**Order (訂單)**:
One Google Form response. One recipient, one address, one ship date, plus the quantities of every item ordered in that response.
_Avoid_: single order / multiple orders (單筆訂單／多筆訂單) — a leftover from the old free-text era. One form response is exactly one order; there is no such thing as "one input containing several orders".

**Ship date (出貨日)**:
The date we send the order out, including the year, chosen by the orderer on the form from a fixed set of options. **Only Wednesdays and Sundays are ship dates**; nothing ships on other days. Orders are filed into tabs by this date.
_Avoid_: arrival date, delivery date (到貨日、送達日) — the customer usually receives the goods after the ship date, so the two must not be mixed up.

**Recipient (收件人)**:
The person who actually receives the goods. The orderer may be someone else (gift scenario); the two need not be the same.
_Avoid_: customer, buyer (客戶、買家)

### Products

**Item (品項)**:
The smallest orderable unit, made up of a combination of "category" and "grade". There are currently four.
_Avoid_: goods, product, SKU (商品、產品、SKU)

**Category (類別)**:
The packaging form. Currently "家庭號" (family pack; one box, two layers, 12 fruits) and "精選禮盒" (select gift box; one box, one layer, 6 fruits).
_Avoid_: product type (產品類型、product type)

**Grade (規格)**:
The fruit grade, currently 18A and 20A. 18A is marketed as "優惠首選" (best-value pick); the 20A select gift box is marketed as "大口滿足" (big-bite satisfaction).
_Avoid_: size, dimensions, level (尺寸、大小、等級)

**Tiered pricing (級距定價)**:
The select gift box is priced per box-count tier as a whole, not unit price times quantity (2 boxes are $1,910, not $1,020×2). Does not apply to the family pack, which is priced linearly per box.
_Avoid_: discount, promotional price (折扣、優惠價)

### Consolidation and notification

**Order cutoff (截單)**:
The point at which a ship date stops accepting orders — the day before that ship date. Orders arriving after the cutoff go to the next ship date.

**Daily report (日報)**:
The details produced by summing all orders for one ship date by item, pushed proactively to the owner after the cutoff. In practice it is the stock-prep and shipping work list for that ship date.
_Avoid_: summary report, summary, report (匯總報告、summary、報表) — "匯總" is the name of the old LINE command, the passive on-demand-query version of the same thing.

**Date tab (日期分頁)**:
Tabs split out of the master order sheet (『表單回覆 1』) by delivery date, inside the same spreadsheet file — one tab per delivery date, with the tab name being the date `YYYY-MM-DD`. It is a projection of the master sheet, not separate data: every run of `python organize_by_date.py --write` rebuilds it entirely, so manual edits are overwritten — make changes in the master sheet instead. When an order's delivery date changes, the tab for its original day is cleared. Orders with a blank or unparseable delivery date are collected in the "未指定日期" (unspecified date) tab.
_Avoid_: backup, sub-sheet (備份、分表) — it is neither a copy nor an independently editable data source.

**Shipping tally (出貨統計)**:
The list of how much stock to prepare for a given delivery date, appended below the order rows on that date tab. One line per "grade + category + per-order quantity", e.g. `20A 禮盒 1盒*2個地址` (20A gift box, 1 box × 2 addresses). "個地址" (addresses) counts order rows, not distinct addresses — one row is one shipment, so two orders to the same address mean packing two parcels.
_Avoid_: item summary (品項匯總) — that is the old LINE command's term, and it counts differently.

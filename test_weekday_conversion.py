"""
測試星期幾轉換功能
"""
import os
from datetime import datetime
from dotenv import load_dotenv
from src.utils.dspy_client import DSPyOrderClient
from src.utils.weekday_converter import WeekdayConverter

# 載入環境變數
load_dotenv()

print("=" * 60)
print("測試星期幾轉換功能")
print("=" * 60)

# 測試 WeekdayConverter
print("\n1. 測試 WeekdayConverter 基本功能")
print("-" * 40)

test_weekdays = ["星期天", "星期三", "星期一", "週五", "禮拜六"]
today = datetime.now()
print(f"今天是: {today.strftime('%Y-%m-%d')} ({WeekdayConverter.get_weekday_name(today)})")
print()

for weekday in test_weekdays:
    date = WeekdayConverter.get_next_weekday_date(weekday)
    formatted = WeekdayConverter.format_date_with_weekday(date) if date else "無法轉換"
    print(f"  {weekday:8} -> {formatted}")

# 測試訂單解析中的日期處理
print("\n2. 測試訂單解析中的星期幾處理")
print("-" * 40)

# 初始化 DSPy 客戶端
client = DSPyOrderClient(
    api_key=os.getenv('OPENAI_API_KEY'),
    model='gpt-4o-mini'
)

# 測試您提供的實際訂單
test_order = """
訂購品項(禮盒/家庭號)：
數量(盒/箱)： 18A禮盒 *4
總金額： 

訂購人：徐奇檍
訂購人電話： 091767778
收件人（可同上!以下免填）：張志文
收件人地址： 桃園市中壢區文化二路273巷
收件人電話：0981768
預計出貨日(星期日/星期三)：星期天
"""

print("原始訂單:")
print(test_order)

# 執行解析
result = client.parse_order(test_order)

if result['success']:
    print("\n解析成功！")
    orders = result['data']['orders']
    if orders:
        order = orders[0]
        shipping_date = order.get('shipping_date')
        
        print(f"\n訂單資訊:")
        print(f"  訂購人: {order.get('sender_name')}")
        print(f"  收件人: {order.get('receiver_name')}")
        print(f"  商品: {order.get('items', [{}])[0].get('name')} x {order.get('items', [{}])[0].get('quantity')}")
        
        if shipping_date:
            formatted_date = WeekdayConverter.format_date_with_weekday(shipping_date)
            print(f"  出貨日期: {formatted_date}")
        else:
            print(f"  出貨日期: 未指定")
else:
    print(f"\n解析失敗: {result.get('error')}")

# 測試其他星期格式
print("\n3. 測試各種星期格式的訂單")
print("-" * 40)

test_cases = [
    "收件人：李小姐 電話：0912345678 地址：台北市信義區 商品：16A蛋糕 *2 出貨：星期三",
    "收件人：王先生 電話：0987654321 地址：高雄市前金區 商品：20A花束 *1 預計星期日送達",
]

for i, test_case in enumerate(test_cases, 1):
    print(f"\n測試案例 {i}:")
    print(f"輸入: {test_case}")
    
    result = client.parse_order(test_case)
    if result['success']:
        order = result['data']['orders'][0]
        shipping_date = order.get('shipping_date')
        
        if shipping_date:
            formatted = WeekdayConverter.format_date_with_weekday(shipping_date)
            print(f"出貨日期: {formatted}")
        else:
            print(f"出貨日期: 未解析")
    else:
        print(f"解析失敗")

print("\n" + "=" * 60)
print("測試完成！")
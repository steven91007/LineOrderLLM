"""
測試日期修復 - 最終版本
"""
import os
from dotenv import load_dotenv
from src.utils.dspy_client import DSPyOrderClient

# 載入環境變數
load_dotenv()

print("測試日期修復...")
print("=" * 50)

# 初始化 DSPy 客戶端
client = DSPyOrderClient(
    api_key=os.getenv('OPENAI_API_KEY'),
    model='gpt-4o-mini'
)

# 測試您的實際訂單
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
print("=" * 50)

# 執行解析
result = client.parse_order(test_order)

if result['success']:
    print("解析成功！")
    orders = result['data']['orders']
    if orders:
        order = orders[0]
        shipping_date = order.get('shipping_date')
        
        print(f"訂購人: {order.get('sender_name')}")
        print(f"收件人: {order.get('receiver_name')}")
        print(f"商品: {order.get('items', [{}])[0].get('name')} x {order.get('items', [{}])[0].get('quantity')}")
        print(f"出貨日期: {shipping_date}")
        
        # 檢查日期是否正確
        from src.utils.weekday_converter import WeekdayConverter
        expected_date = WeekdayConverter.get_next_weekday_date("星期天")
        
        print(f"預期日期: {expected_date}")
        print(f"實際日期: {shipping_date}")
        
        if shipping_date == expected_date:
            print("日期轉換成功！")
            formatted = WeekdayConverter.format_date_with_weekday(shipping_date)
            print(f"格式化日期: {formatted}")
        else:
            print("日期轉換仍有問題")
            
            # 額外測試：直接檢查文字提取
            from src.utils.dspy_modules.unified_parser import UnifiedOrderParser
            parser = UnifiedOrderParser()
            direct_extract = parser._extract_date_from_text(test_order)
            print(f"直接文字提取結果: {direct_extract}")
else:
    print(f"解析失敗: {result.get('error')}")

print("\n" + "=" * 50)
print("測試完成！")
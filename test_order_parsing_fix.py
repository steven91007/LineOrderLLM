"""
測試訂單解析修復
"""
import os
from dotenv import load_dotenv
from src.utils.dspy_client import DSPyOrderClient

# 載入環境變數
load_dotenv()

# 初始化 DSPy 客戶端
client = DSPyOrderClient(
    api_key=os.getenv('OPENAI_API_KEY'),
    model='gpt-4o-mini'
)

# 測試用戶提供的訂單格式
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

print("測試訂單解析...")
print("=" * 50)
print("原始訂單文字:")
print(test_order)
print("=" * 50)

# 執行解析
result = client.parse_order(test_order)

if result['success']:
    print("解析成功！")
    print("\n解析結果:")
    import json
    print(json.dumps(result['data'], ensure_ascii=False, indent=2))
    
    # 驗證關鍵欄位
    orders = result['data']['orders']
    if orders:
        order = orders[0]
        print("\n關鍵欄位檢查:")
        print(f"  訂購人: {order.get('sender_name', '無')}")
        print(f"  訂購人電話: {order.get('sender_phone', '無')}")
        print(f"  收件人: {order.get('receiver_name', '無')}")
        print(f"  收件人電話: {order.get('receiver_phone', '無')}")
        print(f"  收件地址: {order.get('shipping_address', '無')}")
        print(f"  商品項目:")
        for item in order.get('items', []):
            print(f"    - {item['name']} x {item['quantity']}")
else:
    print("解析失敗")
    print(f"錯誤訊息: {result.get('error', '未知錯誤')}")

# 測試其他格式
print("\n" + "=" * 50)
print("測試其他數量格式...")

test_cases = [
    "收件人：李小姐 電話：0912345678 地址：台北市信義區松仁路100號 商品：16A蛋糕 *2",
    "收件人：王先生 電話：0987654321 地址：高雄市前金區中正路200號 商品：20A花束 *1, 18A禮盒 *3",
]

for i, test_case in enumerate(test_cases, 1):
    print(f"\n測試案例 {i}: {test_case}")
    result = client.parse_order(test_case)
    if result['success']:
        order = result['data']['orders'][0]
        print(f"  成功 - 商品: ", end="")
        for item in order.get('items', []):
            print(f"{item['name']} x{item['quantity']}", end=" ")
        print()
    else:
        print(f"  失敗 - {result.get('error', '未知錯誤')}")
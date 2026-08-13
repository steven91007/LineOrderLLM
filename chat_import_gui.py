#!/usr/bin/env python
"""
聊天紀錄匯入訂單的圖形介面

在本機起一個小網頁，貼上聊天紀錄 → 預覽解析結果 → 勾選後寫入 Google 試算表。

用法：
    python chat_import_gui.py

啟動後瀏覽器會自動打開 http://127.0.0.1:5055

這是本機工具，只綁 127.0.0.1，不對外開放。
"""

import logging
import threading
import webbrowser

from flask import Flask, jsonify, render_template, request

import config
from src.services.chat_log_importer import ChatLogImporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

PORT = 5055

# 解析結果暫存在記憶體，讓「寫入」步驟能沿用預覽時算好的資料列，
# 不必為了寫入再呼叫一次 LLM（也避免兩次解析結果不一致）。
_state = {'orders': [], 'importer': None}
_lock = threading.Lock()


@app.route('/')
def index():
    return render_template('chat_import.html')


@app.route('/api/parse', methods=['POST'])
def api_parse():
    payload = request.get_json(silent=True) or {}
    chat_log = (payload.get('chat_log') or '').strip()
    if not chat_log:
        return jsonify({'success': False, 'error': '聊天紀錄是空的'})

    missing = _check_config()
    if missing:
        return jsonify({'success': False, 'error': '設定不完整，缺少：' + '、'.join(missing)})

    model = payload.get('model') or config.DSPY_MODEL
    normalize = bool(payload.get('normalize', True))

    try:
        importer = ChatLogImporter(
            api_key=config.DSPY_API_KEY,
            sheet_id=config.GOOGLE_SHEET_ID,
            credentials_path=config.GOOGLE_CREDENTIALS_PATH,
            model=model,
            normalize_addresses=normalize,
        )
        parsed_orders = importer.parse(chat_log)
    except Exception as error:
        logger.exception('解析失敗')
        return jsonify({'success': False, 'error': str(error)})

    with _lock:
        _state['orders'] = parsed_orders
        _state['importer'] = importer

    return jsonify({
        'success': True,
        'orders': [
            {
                'order': p.order,
                'problems': p.problems,
                'status': p.status,
            }
            for p in parsed_orders
        ],
    })


@app.route('/api/write', methods=['POST'])
def api_write():
    payload = request.get_json(silent=True) or {}
    indices = payload.get('indices') or []

    with _lock:
        parsed_orders = _state['orders']
        importer = _state['importer']

    if not importer or not parsed_orders:
        return jsonify({'success': False, 'error': '沒有可寫入的解析結果，請先按「解析」'})

    try:
        selected = [parsed_orders[i] for i in indices]
    except (IndexError, TypeError):
        return jsonify({'success': False, 'error': '勾選的項目已失效，請重新解析'})

    if not selected:
        return jsonify({'success': False, 'error': '沒有勾選任何訂單'})

    # 使用者在介面上已經逐筆確認過，這裡不再依 status 過濾
    try:
        result = importer.write(selected, include_review=True)
    except Exception as error:
        logger.exception('寫入失敗')
        return jsonify({'success': False, 'error': str(error)})

    if not result.get('success'):
        detail = '；'.join(result.get('mismatches', []))
        error = result.get('error', '未知錯誤')
        return jsonify({'success': False, 'error': f'{error}{"：" + detail if detail else ""}'})

    return jsonify({'success': True, 'appended_rows': result.get('appended_rows', 0)})


def _check_config():
    missing = []
    if not config.DSPY_API_KEY:
        missing.append('OPENAI_API_KEY')
    if not config.GOOGLE_SHEET_ID:
        missing.append('GOOGLE_SHEETS_ID')
    if not config.GOOGLE_CREDENTIALS_PATH:
        missing.append('GOOGLE_SHEETS_CREDENTIALS_PATH')
    return missing


if __name__ == '__main__':
    url = f'http://127.0.0.1:{PORT}'
    print(f'聊天紀錄匯入介面已啟動：{url}')
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    # 只綁 127.0.0.1，不讓區網其他機器連進來
    app.run(host='127.0.0.1', port=PORT, debug=False)

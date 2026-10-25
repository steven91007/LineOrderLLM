#!/usr/bin/env python
"""
GUI for importing orders from chat logs.

Starts a small local web page: paste a chat log → preview the parse results →
tick the orders to write to the Google Sheet.

Usage:
    python chat_import_gui.py

Once started, the browser opens http://127.0.0.1:5055 automatically.

This is a local tool: it binds only to 127.0.0.1 and is not exposed externally.

Note: the Chinese 'error' strings in the JSON responses are shown in the GUI to
shop staff, so they stay in Chinese.
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

# Parse results are cached in memory so the "write" step can reuse the rows computed
# for the preview, without calling the LLM again (which also avoids two parses disagreeing).
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
        logger.exception('Parse failed')
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

    # The user has already confirmed each order in the UI, so no filtering by status here
    try:
        result = importer.write(selected, include_review=True)
    except Exception as error:
        logger.exception('Write failed')
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
    print(f'Chat-log import GUI started: {url}')
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    # Bind only to 127.0.0.1 so other machines on the LAN cannot connect
    app.run(host='127.0.0.1', port=PORT, debug=False)

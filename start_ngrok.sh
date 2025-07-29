#!/bin/bash

# 啟動 Flask 應用
echo "Starting Flask application..."
python main.py &
FLASK_PID=$!

# 當腳本結束時，終止 Flask 應用
trap "kill $FLASK_PID" EXIT

# 等待 Flask 啟動
sleep 5

# 啟動 ngrok
echo "Starting ngrok tunnel..."
ngrok http 5001 --log=stdout
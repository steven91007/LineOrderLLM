#!/bin/bash

# Start the Flask app
echo "Starting Flask application..."
python main.py &
FLASK_PID=$!

# Wait for Flask to start
sleep 5

# Start ngrok
echo "Starting ngrok tunnel..."
ngrok http 5001 --log=stdout

# When the script exits, kill the Flask app
trap "kill $FLASK_PID" EXIT
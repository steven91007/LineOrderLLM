#!/bin/bash

# Create the SSL certificate directory
mkdir -p ssl

# Generate a self-signed certificate
openssl req -x509 -newkey rsa:4096 -nodes -out ssl/cert.pem -keyout ssl/key.pem -days 365 \
    -subj "/C=TW/ST=Taiwan/L=Taipei/O=LineBot/CN=35.78.109.166"

echo "SSL certificate created!"
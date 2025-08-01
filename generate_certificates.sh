#!/bin/bash

if [ -f UI/cert.pem ] || [ -f UI/key.pem ]; then
    echo "SSL certificates already exist. Skipping generation."
else
    echo "Generating self-signed SSL certificates..."
    openssl req -x509 -newkey rsa:4096 -keyout UI/key.pem -out UI/cert.pem -days 365 -nodes
    echo "SSL certificates generated and saved in UI directory."
fi
#!/bin/bash

set -e
if [ -f "/certs/cert.pem" ] && [ -f "/certs/key.pem" ]; then
    echo "Certificates already exist, skipping generation."
else
    echo "Generating certificates..."
    /app/generate_certificates.sh /certs
fi

$HOME/.local/bin/peak-assistant --cert-dir /certs/ --host 0.0.0.0

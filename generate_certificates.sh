#!/bin/bash

set -e

if [ -d "$1" ]; then
    echo "Using directory $1 for SSL certificate generation."
    CERTDIR="$1"
else
    echo "Directory $1 does not exist. Using current directory."
    CERTDIR="."
fi
if [ -f "${CERTDIR}/cert.pem" ] && [ -f "${CERTDIR}/key.pem" ]; then
    echo "SSL certificates already exist. Skipping generation."
else
    echo "Generating self-signed SSL certificates..."
    openssl req -x509 -newkey rsa:4096 -keyout "$CERTDIR/key.pem" -out "$CERTDIR/cert.pem" -days 365 -nodes -subj "/CN=localhost"
    echo "SSL certificates generated and saved in $CERTDIR."
fi
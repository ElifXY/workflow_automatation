#!/usr/bin/env bash
set -euo pipefail

apt-get update
apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu || true

mkdir -p /opt/kanzlei-software
chown -R ubuntu:ubuntu /opt/kanzlei-software

echo "Bootstrap done. Next:"
echo "1) git clone <repo> /opt/kanzlei-software"
echo "2) cp .env.example .env and fill secrets"
echo "3) docker compose up -d --build"

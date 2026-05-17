#!/bin/bash
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive
LOG_FILE="/var/log/webserver-bootstrap.log"
exec > >(tee -a "$LOG_FILE") 2>&1

APP_DIR="/opt/scms"
REPO_URL="${repo_url}"
REPO_BRANCH="${repo_branch}"
REPO_SUBDIR="${repo_subdir}"
GITHUB_USERNAME="${github_username}"
GITHUB_TOKEN="${github_token}"

apt-get update
apt-get install -y ca-certificates curl gnupg git lsb-release apt-transport-https software-properties-common

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo ${VERSION_CODENAME}) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker
usermod -aG docker azureuser || true

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"

REPO_HOST_PATH="$(echo "$REPO_URL" | sed 's#https://##')"
AUTH_REPO_URL="https://${GITHUB_USERNAME}:${GITHUB_TOKEN}@${REPO_HOST_PATH}"

git clone --branch "$REPO_BRANCH" "$AUTH_REPO_URL" "$APP_DIR"

cd "$APP_DIR/$REPO_SUBDIR"
docker compose pull || true
docker compose up -d --build

docker ps

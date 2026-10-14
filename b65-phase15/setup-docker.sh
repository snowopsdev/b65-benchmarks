#!/usr/bin/env bash
# One-time, run by AJ (needs sudo): start Docker now and at boot, and let this user run it.
# Note: the docker group is root-equivalent on this machine.
set -euo pipefail
sudo systemctl enable --now docker.service
sudo usermod -aG docker "$USER"
echo "Docker is running and $USER is in the docker group (log out and back in for new shells; registry_run.sh handles it itself)."
docker --version

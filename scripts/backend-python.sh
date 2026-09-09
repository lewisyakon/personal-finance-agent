#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_PYTHON="${ROOT_DIR}/.venv/bin/python"

if [[ -x "${PROJECT_PYTHON}" ]] && "${PROJECT_PYTHON}" -c 'import sys; print(sys.version)' >/dev/null 2>&1; then
  exec "${PROJECT_PYTHON}" "$@"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "项目虚拟环境无法在当前宿主机启动，且未找到 Docker。请安装 Python 3.12 或 Docker。" >&2
  exit 1
fi

# Ubuntu 20.04 in the development host has an older GLIBC than the selected
# Python 3.12 build. The process still runs as lewis and writes only to the
# mounted project directory; Docker is used as a runtime compatibility layer.
exec docker run --rm --network host --user "$(id -u):$(id -g)" \
  -v "${ROOT_DIR}:/workspace" -w /workspace/backend \
  python:3.12-slim \
  /workspace/.venv/bin/python "$@"


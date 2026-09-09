#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
NODE_BIN="${HOME}/.local/node-v20.17.0-linux-x64/bin"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "未找到 ${ROOT_DIR}/.venv，请先按 README 创建虚拟环境。" >&2
  exit 1
fi

if [[ ! -x "${NODE_BIN}/npm" ]]; then
  echo "未找到用户级 Node.js，请先按 README 配置 Node.js。" >&2
  exit 1
fi

export PATH="${NODE_BIN}:${ROOT_DIR}/.venv/bin:${PATH}"

cleanup() {
  kill 0 2>/dev/null || true
}
trap cleanup INT TERM EXIT

(
  cd "${ROOT_DIR}/backend"
  exec "${PYTHON_BIN}" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
) &

(
  cd "${ROOT_DIR}/frontend"
  exec npm run dev
) &

wait


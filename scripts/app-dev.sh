#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE_BIN="${HOME}/.local/node-v20.17.0-linux-x64/bin"

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
  exec "${ROOT_DIR}/scripts/backend-python.sh" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
) &

(
  cd "${ROOT_DIR}/frontend"
  exec npm run dev
) &

wait

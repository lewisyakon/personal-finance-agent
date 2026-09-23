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
# Python 3.12 build. Build/run the project image instead of trying to execute
# the host-created .venv inside an unrelated Python container. Compose mounts
# only the source/data directories and keeps the process on the caller's UID.
if [[ -f "${ROOT_DIR}/docker-compose.yml" ]]; then
  export PFA_BACKEND_EXTRAS="${PFA_BACKEND_EXTRAS:-[dev]}"
  exec "${ROOT_DIR}/scripts/docker-compose.sh" run --rm --no-deps --build \
    --service-ports backend python "$@"
fi

echo "未找到项目 Docker Compose 配置，无法启动隔离的 Python 3.12 运行时。" >&2
exit 1

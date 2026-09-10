#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v docker >/dev/null 2>&1; then
  echo "未找到 Docker，请先安装 Docker Engine 和 Docker Compose。" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "当前 Docker 不包含 Compose 插件，请安装 docker compose。" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "无法连接 Docker daemon。请启动 Docker Engine，并确认当前用户有权访问 docker.sock。" >&2
  exit 1
fi

# A stale/missing docker0 interface makes BuildKit fail before it even reaches
# the Dockerfile. Detect that state early and avoid a misleading build error.
if command -v ip >/dev/null 2>&1; then
  bridge_name="$(docker network inspect bridge \
    --format '{{index .Options "com.docker.network.bridge.name"}}' 2>/dev/null || true)"
  if [[ -n "${bridge_name}" ]] && ! ip link show dev "${bridge_name}" >/dev/null 2>&1; then
    echo "Docker bridge 网络引用了不存在的 ${bridge_name} 接口。请先执行：sudo systemctl restart docker；" >&2
    echo "然后确认 'ip link show ${bridge_name}' 和 'docker network inspect bridge' 均正常。" >&2
    exit 1
  fi
fi

# Keep files created in mounted data/source directories owned by the caller.
export PFA_UID="${PFA_UID:-$(id -u)}"
export PFA_GID="${PFA_GID:-$(id -g)}"

cd "${ROOT_DIR}"
exec docker compose -f "${ROOT_DIR}/docker-compose.yml" "$@"

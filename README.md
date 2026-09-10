# 个人消费分析多智能体系统

本仓库按《个人消费分析多智能体系统开发规格》分阶段实现。本次交付完成：

- 阶段 0：Vue 3 + TypeScript + Vite、FastAPI、SQLite/WAL、Alembic、mock ModelProvider、VS Code 任务和基础测试。
- 阶段 1：微信账单 CSV/XLSX Parser，CSV 支持 UTF-8/UTF-8 BOM/GB18030/UTF-16 尝试，二者均支持表头识别、金额/时间/方向/状态标准化、行级错误和 Golden Test。
- 阶段 2：账单导入任务、HMAC 去重、SQLite 交易持久化、分页筛选、交易详情和人工分类审计；前端提供导入记录与交易管理页面。

当前 Parser 支持微信 CSV 和 XLSX；ZIP 会在脱敏样例确实需要时按阶段扩展。Parser 不调用 LLM。

## 阶段 2 使用说明

启动 API 后访问 `/imports` 上传微信 CSV/XLSX，或直接调用：

```bash
curl -F 'file=@datasets/sanitized_samples/wechat_sample_utf8.csv' \
  http://127.0.0.1:8000/api/v1/imports
curl -F 'file=@/home/lewis/pfa-validation-data/wechat-2026.xlsx' \
  http://127.0.0.1:8000/api/v1/imports
curl 'http://127.0.0.1:8000/api/v1/transactions?page=1&page_size=20'
```

导入接口根据文件扩展名自动识别 `csv` 或 `xlsx`；也可以显式传 `?format=csv` 或 `?format=xlsx`，但格式必须和文件扩展名一致。接口在本地使用进程内执行器同步完成。每个工作区以 `LOCAL_OWNER_ID` 隔离；交易指纹使用 `FINGERPRINT_SECRET` 计算 HMAC-SHA256，数据库在 owner 范围内建立唯一约束。同一文件的 SHA-256 已存在时直接复用原导入任务，不会重复入账。原始文件只在 `RAW_FILE_TTL_MINUTES` 到期后清理，数据库保留文件摘要和标准化事实。

这里的 `PFA_DATA_DIR` 是后端数据库、上传临时文件和日志的存储目录；使用
`curl -F file=@...` 时，`@` 后面的路径由运行 `curl` 的服务器 shell 读取，可以与
`PFA_DATA_DIR` 相同，也可以位于其他目录。

阶段 2 API：

- `POST /api/v1/imports`、`GET /api/v1/imports`、`GET /api/v1/imports/{id}`、`POST /api/v1/imports/{id}/retry`、`DELETE /api/v1/imports/{id}`。
- `GET /api/v1/transactions`（分页、时间、方向、状态、分类、商户筛选）、`GET /api/v1/transactions/{id}`。
- `PATCH /api/v1/transactions/{id}/category`，响应包含修改前后分类；审计记录写入 `transaction_category_changes`。

首次启动会自动创建本地表；生产/升级环境请使用 Alembic：`cd backend && alembic upgrade head`。

## 用户目录安装

项目不要求 root 权限。推荐使用用户目录中的 Python 3.12（例如 `uv python install 3.12`）创建虚拟环境：

```bash
cd personal-finance-agent
source scripts/user-runtime.sh
~/.local/bin/uv venv --python 3.12 .venv
source .venv/bin/activate
python -m pip install -e './backend[dev]'
cd frontend && npm install
```

如果没有 `uv`，也可以使用已经安装的 Python 3.12 创建 `.venv`。不要将真实账单、API Key 或 `.env` 提交到 Git。

## 开发命令

```bash
# 后端；脚本优先使用本机 Python 3.12，Ubuntu 20.04 上自动使用非 root 的 Python 3.12 容器运行时
cd backend && ../scripts/backend-python.sh -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 前端
cd frontend && npm run dev

# 后端测试与检查
cd backend && ../scripts/backend-python.sh -m pytest && ../scripts/backend-python.sh -m ruff check app tests

# 前端构建、测试与类型检查
cd frontend && npm run typecheck && npm test && npm run build
```

默认 API 地址为 `http://127.0.0.1:8000`，前端地址为 `http://127.0.0.1:5173`。

如果需要同时启动前后端：

```bash
./scripts/app-dev.sh
```

## Docker 开发环境

如果宿主机没有可用的 Python 3.12（例如项目 `.venv` 是在另一个 Python 镜像中创建的），可以使用仓库内的 Docker Compose 配置。镜像会在容器内安装后端依赖，宿主机不需要把依赖安装到系统 Python，也不会改写宿主机的全局 `site-packages`：

```bash
# 启动后端；首次运行会构建 python:3.12-slim 镜像
./scripts/docker-compose.sh up --build backend

# 如果 PyPI 国际链路较慢，可只为构建指定镜像（示例为清华镜像）
PFA_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  ./scripts/docker-compose.sh up --build backend

# 如果 Docker bridge/DNS 路径不稳定，可让“构建步骤”使用宿主机网络。
# 这不会改变容器运行时的 bridge 网络或 127.0.0.1 端口绑定。
PFA_BUILD_NETWORK=host ./scripts/docker-compose.sh up --build backend

# 停止并移除 Compose 创建的容器（不会删除挂载的 data/）
./scripts/docker-compose.sh down

# 或用同一个镜像运行检查和测试
./scripts/backend-python.sh -m pytest
./scripts/backend-python.sh -m ruff check app tests
```

Docker 运行时的边界是显式挂载的目录和端口：

- `backend/` 挂载到容器用于热重载，编辑器中的代码修改会即时生效；
- `data/` 挂载到容器，SQLite 数据库和上传文件因此与宿主机项目共享，这是有意的持久化行为；
- `datasets/` 以只读方式挂载；`.venv`、Node.js、系统 Python 和其他宿主机目录不会挂载；
- `data/` 和 `datasets/` 也不会被复制进镜像构建层，避免账单内容进入镜像缓存；
- API 只绑定宿主机 `127.0.0.1:8000`，不会默认暴露到局域网或公网。

因此，容器本身删除后不会留下容器级依赖或进程；挂载目录中的数据库、上传文件和代码修改会保留。首次启动前如果不希望触碰当前账本，可以备份 `data/personal_finance.db`，或把 Compose 中的 `./data` 改为单独的测试目录。脚本会把容器进程设置为当前用户的 UID/GID，避免在项目目录生成 root 所有的文件。

要完全隔离一次测试的数据，可以把数据挂载点临时切换到 `/tmp`（容器退出后删除该目录即可）：

```bash
PFA_DATA_DIR="$(mktemp -d)" ./scripts/docker-compose.sh run --rm --no-deps --build \
  --service-ports backend python -m pytest
```

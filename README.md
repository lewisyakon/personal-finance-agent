# 个人消费分析多智能体系统

本仓库按《个人消费分析多智能体系统开发规格》分阶段实现。本次交付完成：

- 阶段 0：Vue 3 + TypeScript + Vite、FastAPI、SQLite/WAL、Alembic、mock ModelProvider、VS Code 任务和基础测试。
- 阶段 1：微信账单 CSV/XLSX Parser，CSV 支持 UTF-8/UTF-8 BOM/GB18030/UTF-16 尝试，二者均支持表头识别、金额/时间/方向/状态标准化、行级错误和 Golden Test。
- 阶段 2：账单导入任务、HMAC 去重、SQLite 交易持久化、分页筛选、交易详情和人工分类审计；前端提供导入记录与交易管理页面。
- 阶段 3：确定性统计服务、统计 API、统计口径文档和 Dashboard；支持收支汇总、趋势、
  分类构成、商户排行、大额交易、固定/可变支出、预算和环比/同比。
- 阶段 4：9 个受控只读 Tool、服务端 OwnerContext、严格 Schema、超时与分页、持久化
  Tool Trace，以及 Owner 范围内的 `evidence_id` 快照重放。
- 阶段 5：mock/local/remote OpenAI-compatible ModelProvider、有界 LangGraph Single-Agent、
  会话与运行 API、数值 grounding、最小化模型 Trace，以及固定 30 题评测基线。
- 阶段 6：规则优先 Semantic Agent、商户归一化、历史证据、低置信度待确认和用户确认规则。
- 阶段 7：固定 Supervisor/Analysis/Verifier 图、严格 Handoff、确定性 Verifier、节点 Trace、
  简单问题快路径及 Single/Multi 同题对比。
- 阶段 8：结构化 Planner、任务图校验、依赖波并行执行、一次有界重规划、确定性 Budget Agent
  和预算/分歧确认门禁。
- 阶段 9：本地 Developer Console、Run/计划/Evidence/记忆 Trace、版本化失败样本，以及
  Single/Multi/Multi+Verifier 三架构量化对比。
- 阶段 10：区分会话/长期/知识的用户可控记忆、来源与版本链、过期/删除、检索 hit/miss Trace
  和记忆管理页面。
- 阶段 11：仅回环访问的 Local Web 发行、固定数据目录、显式导出/删除、SQLite 备份恢复、
  升级前保护备份、恶意文件/提示注入防护和 Agent 资源上限。

当前 Parser 支持微信 CSV 和 XLSX；ZIP 会在脱敏样例确实需要时按阶段扩展。Parser 不调用 LLM。

## 使用说明

阶段 3 使用 SQLite 文件数据库，不需要在宿主机安装或启动独立的 SQLite 服务。
Python 自带 `sqlite3`，SQLAlchemy 会直接读写 `PFA_DATA_DIR/personal_finance.db`；
Docker 运行时只是把同一个数据目录挂载到容器内。

启动 API 后访问 `/imports` 上传微信 CSV/XLSX，或直接调用：

```bash
curl -F 'file=@datasets/sanitized_samples/wechat_sample_utf8.csv' \
  http://127.0.0.1:8000/api/v1/imports
curl -F 'file=@/home/lewis/pfa-validation-data/wechat-2026.xlsx' \
  http://127.0.0.1:8000/api/v1/imports
curl 'http://127.0.0.1:8000/api/v1/transactions?page=1&page_size=20'
curl 'http://127.0.0.1:8000/api/v1/stats/summary?from=2026-01-01&to=2026-02-01T00:00:00%2B08:00'
```

导入接口根据文件扩展名自动识别 `csv` 或 `xlsx`；也可以显式传 `?format=csv` 或 `?format=xlsx`，但格式必须和文件扩展名一致。接口在本地使用进程内执行器同步完成。每个工作区以 `LOCAL_OWNER_ID` 隔离；交易指纹使用 `FINGERPRINT_SECRET` 计算 HMAC-SHA256，数据库在 owner 范围内建立唯一约束。同一文件的 SHA-256 已存在时直接复用原导入任务，不会重复入账。原始文件只在 `RAW_FILE_TTL_MINUTES` 到期后清理，数据库保留文件摘要和标准化事实。

微信导出状态中的“已存入零钱”“对方已收钱”“已转账”“已收钱”会标准化为成功；
“已全额退款”“已退款¥0.56”“已退款(¥0.56)”等已完成退款变体会标准化为退款。
微信交易类型中的“转账”优先于“收/支”列，因此收入或支出方向的普通转账都会标准化为
`transfer`；微信退款成对记录中的原始支出保留为支出，实际收入方向的退款行才计入退款回款。
如果同一文件已经在旧版本 Parser 下导入过，幂等规则会复用旧任务，不会自动重解析；
要应用新的状态映射，请先在导入页面删除旧任务（这会级联删除该任务的交易），再重新上传原文件。

这里的 `PFA_DATA_DIR` 是后端数据库、上传临时文件和日志的存储目录；使用
`curl -F file=@...` 时，`@` 后面的路径由运行 `curl` 的服务器 shell 读取，可以与
`PFA_DATA_DIR` 相同，也可以位于其他目录。

阶段 2 API：

- `POST /api/v1/imports`、`GET /api/v1/imports`、`GET /api/v1/imports/{id}`、`POST /api/v1/imports/{id}/retry`、`DELETE /api/v1/imports/{id}`。
- `GET /api/v1/transactions`（分页、时间、方向、状态、分类、商户筛选）、`GET /api/v1/transactions/{id}`。
- `PATCH /api/v1/transactions/{id}/category`，响应包含修改前后分类；审计记录写入 `transaction_category_changes`。

阶段 3 API：

- `GET /api/v1/stats/summary`：收支、净流量、交易数、退款、固定/可变支出和可选预算。
- `GET /api/v1/stats/categories`、`/trend`、`/merchants`：分类构成、日/周/月/年趋势和排行。
- `GET /api/v1/stats/large-transactions`、`/fixed-variable`、`/budget`、`/comparison`：
  大额交易、固定/可变支出、预算状态及环比/同比。
- 前端 Dashboard 地址为 `/dashboard`，首页和顶部导航均提供入口。点击大额交易可跳转
  到交易管理页继续查看详情；页面金额只做分到元的显示换算，权威统计来自后端。

阶段 4 Tool：

- 第一批只读 Tool 包含汇总、分类、趋势、商户、大额交易、交易搜索、周期比较、预算状态
  和商户历史。
- Tool 在后端内部通过 Registry 和 `ToolExecutor` 调用，不新增公开 Tool HTTP 路由。
- Owner 只从可信运行时上下文注入，不出现在模型可见的参数 Schema 中。每次调用都生成
  `evidence_id` 并写入最小化 Trace，结果可在同一 Owner 内校验摘要后重放。

阶段 5 Agent：

- `POST /api/v1/agent/chat` 发起同步查账；会话、运行查询和协作式取消位于
  `/api/v1/agent/sessions/*`、`/api/v1/agent/runs/*`。
- `LLM_PROVIDER=mock|local|remote` 通过环境变量切换。local 只允许回环地址；remote 的非
  回环地址必须是 HTTPS 且必须配置 API Key。服务不可用时明确失败，不静默回退。
- 模型每轮最多选择一个阶段 4 Tool；金额、数量和比例结论由 Tool evidence 做确定性校验，
  不通过时返回“无法确定”。模型 Trace 不保存完整 prompt、上下文或 reasoning。
- 30 题数据集覆盖全部 9 个 Tool，记录 Tool 选择、证据数值、延迟和 Token，默认门槛 80%。

阶段 6 Semantic Agent：

- `POST /api/v1/semantic/transactions/{id}/classify` 先查用户规则、平台分类和历史，均无法判定
  时才调用模型；低于置信度阈值的建议保持 `pending`。
- `/api/v1/semantic/suggestions/*` 支持确认/拒绝，`/api/v1/semantic/rules` 支持查询和删除。
  用户确认规则优先于后续模型结果，已确认商户不会重复调用模型。

阶段 7 Multi-Agent：

- `/api/v1/agent/chat` 支持 `workflow=auto|single|multi`；auto 保留简单查账的 Single-Agent
  快路径，复杂问题进入固定 `Supervisor -> Analysis -> Verifier` 图。
- `POST /api/v1/agent/compare` 对同一问题运行两种工作流；Run 响应包含最小化节点 Trace。
- `python -m app.evals.runner --workflow compare` 在同一 30 题数据集上输出通过率、Tool 选择、
  数值准确率、延迟和 Token 差值。当前只验收确定性 mock；真实 Ollama/远程模型待配置后执行。

阶段 8 Planner 与 Budget Agent：

- `/api/v1/agent/chat` 支持 `workflow=planner`；任务图先校验 Agent/Tool/参数/依赖/循环，再按
  拓扑波次并行执行无依赖任务，最多进行一次 Evidence 驱动重规划。
- `/api/v1/budgets` 管理确定性统计生成的预算草案；`/api/v1/agent/confirmations` 处理预算与
  结果分歧。预算未经用户确认不会成为长期偏好。

阶段 9 Developer Console：

- 前端 `/developer` 展示 Run 节点、计划版本、Tool Evidence、延迟、错误、评测和失败样本；后端
  `/api/v1/developer/*` 只在本地/开发/测试模式并显式启用时开放。
- `python -m app.evals.runner --workflow architecture` 用同一 30 题数据集比较 Single、未验证
  Multi 和 Multi+Verifier。当前按要求仅验收 mock；不宣称真实 Ollama/远程模型质量基线。

阶段 10 用户可控记忆：

- 前端 `/memories` 和 `/api/v1/memories` 支持查看、显式创建、版本化修改和软删除。
- 记忆区分 `session`、`long_term`、`knowledge`；只保存 `user_confirmed` 来源。模型自动分类、
  推测和未确认预算不会写入长期记忆，已删除/过期记录不会注入 Planner。
- `/api/v1/memories/accesses` 和 Developer Console 显示检索 `hit`/`miss` 与匹配 ID，查询原文
  仅保存 SHA-256 指纹。

阶段 11 本地发行与安全：

- 前端 `/settings` 管理导出、SQLite 备份/恢复和删除全部数据；所有动作需要输入精确确认短语，
  删除和恢复还会先显示不可逆/覆盖警告。
- `DATA_DIR` 固定承载数据库、短期上传、日志和备份。上传 XLSX 会检查路径穿越、条目/解压大小、
  压缩比与加密标记；账单文本作为不可信 Tool 数据，不能扩大系统提示或只读 Tool 权限。
- 数据管理 API 见 `/api/v1/data/*`。本地发行只绑定回环地址，Host 白名单默认拒绝非本机请求。

默认 mock 不访问网络，可直接体验基本查账。使用 Ollama 等本地 OpenAI-compatible 服务：

```bash
export LLM_PROVIDER=local
export LLM_BASE_URL=http://127.0.0.1:11434/v1
export LLM_MODEL=your-local-model
```

使用远程兼容服务：

```bash
export LLM_PROVIDER=remote
export LLM_BASE_URL=https://provider.example/v1
export LLM_MODEL=your-model
export LLM_API_KEY='read-from-your-secret-manager'
```

统计边界、退款、转账、失败交易、多币种和比较定义见
[`docs/data-contracts/stage3-stats.md`](docs/data-contracts/stage3-stats.md)。
Tool Schema、错误、分页和 evidence 语义见
[`docs/data-contracts/stage4-tools.md`](docs/data-contracts/stage4-tools.md)。
ModelProvider、Single-Agent 和评测契约见
[`docs/data-contracts/stage5-model-agent.md`](docs/data-contracts/stage5-model-agent.md)，Agent API
见 [`docs/api/stage5-agent.md`](docs/api/stage5-agent.md)。
Semantic 分类合同和 API 见
[`docs/data-contracts/stage6-semantic.md`](docs/data-contracts/stage6-semantic.md)、
[`docs/api/stage6-semantic.md`](docs/api/stage6-semantic.md)。Multi-Agent 合同和 API 见
[`docs/data-contracts/stage7-multi-agent.md`](docs/data-contracts/stage7-multi-agent.md)、
[`docs/api/stage7-multi-agent.md`](docs/api/stage7-multi-agent.md)。
Planner、可观测性和记忆合同/API 分别见
[`docs/data-contracts/stage8-planning.md`](docs/data-contracts/stage8-planning.md)、
[`docs/api/stage8-planning.md`](docs/api/stage8-planning.md)、
[`docs/data-contracts/stage9-observability.md`](docs/data-contracts/stage9-observability.md)、
[`docs/api/stage9-observability.md`](docs/api/stage9-observability.md)、
[`docs/data-contracts/stage10-memory.md`](docs/data-contracts/stage10-memory.md) 和
[`docs/api/stage10-memory.md`](docs/api/stage10-memory.md)。
阶段 11 安全合同、数据 API 与发行决策见
[`docs/data-contracts/stage11-security.md`](docs/data-contracts/stage11-security.md)、
[`docs/api/stage11-data-management.md`](docs/api/stage11-data-management.md) 和
[`docs/adr/0001-local-web-release.md`](docs/adr/0001-local-web-release.md)。
仓库中的 [`datasets/sanitized_samples/stage3_stats_fixture.csv`](datasets/sanitized_samples/stage3_stats_fixture.csv)
是可重复导入的合成核对夹具，文档中列出了该夹具的手工期望总数。

## 阶段 3 至 11 验收

后端测试使用临时数据目录，不会触碰当前的 `pfa-validation-data`。在服务器上执行：

```bash
cd ~/personal-finance-agent
TEST_DATA_DIR="$(mktemp -d)"

PFA_DATA_DIR="$TEST_DATA_DIR" \
PFA_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  ./scripts/docker-compose.sh build backend

PFA_DATA_DIR="$TEST_DATA_DIR" \
  ./scripts/docker-compose.sh run --rm --no-deps backend python -m pytest

PFA_DATA_DIR="$TEST_DATA_DIR" \
  ./scripts/docker-compose.sh run --rm --no-deps backend python -m ruff check app tests
```

前端依赖已安装时：

```bash
cd ~/personal-finance-agent/frontend
npm run typecheck
npm test -- --run
npm run build
npm run lint
```

首次启动会自动创建本地表；由 Alembic 管理的生产/升级环境请使用：
`cd backend && alembic upgrade head`。阶段 4 会新增 `tool_traces` 表；阶段 6/7 新增语义分类、
用户规则和 Multi-Agent Trace 表。未使用 Alembic 管理的
本地 MVP 数据库会在启动新版服务时先创建 `pre_upgrade` 保护备份，再由 `create_all` 补齐新表并
为已有表安全补充兼容列；
阶段 8 至 10 新增 Planner/预算/确认、评测指标/失败样本、版本化记忆及访问 Trace 表。不要对
未 stamp 的既有数据库直接套用初始迁移。

由 Alembic 管理的本地库使用以下命令升级；它会在发现旧版本时先创建一致性备份：

```bash
./scripts/docker-compose.sh run --rm --no-deps backend python -m app.data_admin upgrade
```

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

## Docker 环境

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

Docker 运行时的边界是显式挂载的数据目录和回环端口：

- `PFA_DATA_DIR`（默认 `data/`）挂载到容器，SQLite、短期上传和备份因此持久化；
- 后端代码构建进镜像，不在发行容器内挂载或热重载；`.venv` 和其他宿主机目录不会挂载；
- `data/` 和 `datasets/` 也不会被复制进镜像构建层，避免账单内容进入镜像缓存；
- API 和前端分别只绑定宿主机 `127.0.0.1:8000`、`127.0.0.1:5173`，不会默认暴露到局域网或公网。

因此，容器本身删除后不会留下容器级依赖或进程；挂载目录中的数据库、上传文件和代码修改会保留。首次启动前如果不希望触碰当前账本，可以备份 `data/personal_finance.db`，或把 Compose 中的 `./data` 改为单独的测试目录。脚本会把容器进程设置为当前用户的 UID/GID，避免在项目目录生成 root 所有的文件。

要完全隔离一次测试的数据，可以把数据挂载点临时切换到 `/tmp`（容器退出后删除该目录即可）：

```bash
PFA_DATA_DIR="$(mktemp -d)" ./scripts/docker-compose.sh run --rm --no-deps --build \
  --service-ports backend python -m pytest
```

## 本地发行

```bash
# 默认持久化到仓库 data/；也可先 export PFA_DATA_DIR=/绝对/目录
./scripts/local-release.sh
```

随后只在本机访问 `http://127.0.0.1:5173`。停止服务使用 `./scripts/docker-compose.sh down`；
该命令不会删除 `PFA_DATA_DIR`。普通本地库在兼容升级前自动备份；仅当数据库已经由 Alembic
管理时使用 `app.data_admin upgrade`。也可以先在设置页创建手工备份。发行选择与恢复演练见
阶段 11 文档。

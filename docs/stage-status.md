# 阶段状态

## 阶段 0：工程基线

- 状态：已实现；前端与后端静态检查已通过，Docker 运行态已验证，状态接口和前端访问链路正常。
- 范围：目录骨架、FastAPI 状态接口、SQLite WAL、Alembic 配置、mock Provider、Vue 首页、VS Code 配置、基础测试。

## 阶段 1：微信账单 Parser

- 状态：已实现；前端 typecheck/Vitest/build/lint 与后端 Ruff/语法检查已通过，Docker 运行态已验证，Parser/API 链路可用。
- 范围：CSV、微信 XLSX、编码尝试、微信表头识别、金额/时间/方向/状态标准化、行级错误、3 个合成样例和 Golden Test。
- 未包含：其他 Excel 格式、ZIP、去重、入库、分类和统计。

## 阶段 2：导入、去重与交易管理

- 状态：已实现并完成运行态验收；前端 typecheck/Vitest/build/lint、后端 Ruff/语法检查、Docker 镜像构建、容器启动和前后端接口冒烟验证均已通过。
- 范围：`WorkspaceOwner`、`BillImport`、`Transaction` 和分类修改审计表；进程内导入执行器；owner 范围 HMAC-SHA256 指纹和数据库唯一约束；重复文件幂等、重试、导入报告计数、原始文件 TTL 清理；导入和交易管理 API；Vue 导入记录与交易管理页面。
- 约束：当前只接受微信 CSV/XLSX；不调用模型；模型和客户端不能指定 owner_id；金额以整数最小货币单位存储；原始文件不进入日志和数据库内容字段。
- 已知限制：导入任务为同步进程内执行；ZIP 和更复杂的分类规则属于后续阶段；SQLite 日期列由服务按带时区输入查询并在 API 中返回 ISO 时间。

验收重点：

```bash
cd backend && pytest && ruff check app tests
cd ../frontend && npm run typecheck && npm test && npm run build
```

Docker 运行态验收记录：

- `python:3.12-slim` 后端镜像构建成功，依赖安装完成。
- Compose 网络和后端容器启动成功，Uvicorn 监听容器 `8000` 端口。
- `GET /` 和 `GET /api/v1/system/status` 均返回 `200 OK`。
- 前后端接口联调通过；停止 Compose 后容器正常退出。

## 阶段 3：统计服务与 Dashboard

- 状态：实现及本地运行级验收完成；统计 API、统计口径文档、合成数据准确性测试和
  ECharts Dashboard 已加入，统计准确性门禁已通过。
- 当前本地验证：后端 `pytest` 21 项通过，Ruff 和 Python 语法检查通过；前端
  `typecheck`、Vitest（2 项）、`build` 和 `lint` 均通过。同步 API 测试客户端使用
  项目已有的 uvloop，避免特定沙箱默认线程桥接不返回。
- 本地 ASGI 运行级冒烟已通过：临时 SQLite 数据目录中的 `system/status`、合成 12 行账单
  导入、`summary`、`categories` 和月度 `trend` 均返回预期结果；服务器 Docker 构建和
  容器网络验收仍需在目标服务器执行。
- 范围：确定性 `Stats Service`、汇总/分类/趋势/商户/大额交易/固定可变/预算/环比同比
  API、单币种校验、退款/转账/失败交易和时间边界口径、Dashboard 展示与交易下钻。
- 约束：前端只消费 API 结果，不重新计算权威统计；金额仍以整数最小货币单位存储；
  统计服务不调用模型；用户人工分类修改后统计即时读取最新分类。
- 微信兼容规则：交易类型包含“转账”时优先标准化为 `transfer`；退款成对记录中，
  原始支出保留为支出，收入方向的实际退款行计入 `refund_minor`。
- 统计口径详见 [`docs/data-contracts/stage3-stats.md`](data-contracts/stage3-stats.md)，
  API 详见 [`docs/api/stage3-stats.md`](api/stage3-stats.md)。

验收重点：

```bash
cd backend && pytest && ruff check app tests
cd ../frontend && npm run typecheck && npm test && npm run build
```

## 阶段 4：受控 Tool

- 状态：实现完成；9 个第一批只读 Tool、OwnerContext 注入、严格参数 Schema、超时、分页、
  `evidence_id`、持久化 Trace 和 Owner 范围内快照重放已加入。
- Tool：`get_spending_summary`、`get_category_breakdown`、`get_trend`、
  `get_top_merchants`、`get_large_transactions`、`search_transactions`、
  `compare_periods`、`get_budget_status`、`get_merchant_history`。
- 统计一致性：统计 Tool 直接调用阶段 3 `Stats Service`，不复制统计计算；金额、时间、
  退款、转账、失败交易和多币种口径保持一致。
- 隔离与安全：Provider Schema 中没有 `owner_id`；额外 Owner 参数会被拒绝；交易搜索只接受
  固定筛选条件，不接受 SQL、路径或 URL；Trace 不保存完整账单行或平台交易标识。
- Evidence：每次成功或失败调用都写入 `tool_traces`，请求/响应分别带 SHA-256 摘要；
  `evidence_id` 只能由所属 Owner 重放，重放返回调用时的不可变快照。
- 当前验证：后端 `pytest` 27 项通过，Ruff 通过。新增测试覆盖全部 Tool、Stats Service
  一致性、分页/结果上限、Owner 越权、结构化错误、超时、Trace 完整性和 evidence 重放；
  全新 SQLite 的 Alembic `upgrade head` 通过；未改动前端的 `typecheck`、Vitest（2 项）、
  `build` 和 `lint` 回归通过。
- 阶段 4 不包含模型、Single-Agent 或公开 Tool HTTP 路由；这些属于阶段 5。

合同详见 [`docs/data-contracts/stage4-tools.md`](data-contracts/stage4-tools.md)，内部调用接口
详见 [`docs/api/stage4-tools.md`](api/stage4-tools.md)。由 Alembic 管理的数据库升级需执行：

```bash
cd backend && alembic upgrade head
```

## 阶段 5：ModelProvider 与 Single-Agent

- 状态：实现完成；Provider、Single-Agent、Agent API、持久化 Trace、数值 grounding 和
  30 题评测基线已加入。
- Provider：通过 `LLM_PROVIDER=mock|local|remote` 切换；local 只连回环地址，remote 强制
  非回环 HTTPS 和 API Key；支持普通消息、Tool calling、JSON Schema 输出、超时、有界重试、
  取消、健康检查、延迟和 Token 统计。故障显式返回，不静默降级。
- Single-Agent：LangGraph 执行 `model -> 单个只读 Tool -> model` 有界循环，复用阶段 4 全部
  9 个 Tool；Owner 由服务端注入。步数、Tool/模型调用数、总时长和 Token 均有限制。
- Grounding：查账回答必须含成功 evidence；带金额、比例和笔数单位的关键数字必须存在于
  Tool 结果，否则以 `UNGROUNDED_NUMERIC_CLAIM` 失败并隐藏错误数值。
- 可观测性：会话、Run、Provider/模型、延迟、Token、选中 Tool、错误码和 evidence 持久化；
  模型 Trace 不保存完整 prompt、Tool 上下文、API Key 或 reasoning。
- API：`POST /api/v1/agent/chat`，会话/Run 查询和取消端点；所有数据按 Owner 隔离。
- 评测：`stage5-v1` 固定 30 题覆盖全部 9 个 Tool，门槛 80%；确定性 mock 编排基线达到
  100% Tool 选择准确率和 100% evidence 数值准确率。local/remote 模型需用同一命令单独留档。
- 数据库：迁移 `20260920_0003` 新增 Agent/评测表，并把 Tool Evidence 与 Run 关联。
- 当前验证：后端 40 项测试与 Ruff 全部通过；Alembic `check` 无待生成操作，完整
  downgrade/upgrade 往返通过；临时 SQLite 上的状态接口和 Agent 查账运行态冒烟通过；前端
  typecheck、Vitest（2 项）、build 和 lint 回归通过。

合同详见
[`docs/data-contracts/stage5-model-agent.md`](data-contracts/stage5-model-agent.md)，HTTP API 详见
[`docs/api/stage5-agent.md`](api/stage5-agent.md)。

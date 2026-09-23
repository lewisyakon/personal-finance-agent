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

## 阶段 6：Semantic Agent

- 状态：实现完成；规则优先分类、Semantic Agent、低置信度待确认、用户规则和 HTTP API 已加入。
- 路由顺序：用户确认规则 > 平台明确分类 > 同商户一致历史 > 模型；前三条命中时不调用模型。
- 验收覆盖：已确认商户不重复调用模型；低置信度进入 `pending`；确认可生成长期规则；用户修正
  优先于模型；高置信度仅应用当前交易而不自动保存规则；Owner 范围和 API 管理链路通过。
- Evidence：规则/平台使用稳定引用；历史与模型路径使用阶段 4 `get_merchant_history` 快照。
- 数据库：迁移 `20260921_0004` 新增 `merchant_rules` 和 `classification_suggestions`。

合同见 [`docs/data-contracts/stage6-semantic.md`](data-contracts/stage6-semantic.md)，API 见
[`docs/api/stage6-semantic.md`](api/stage6-semantic.md)。

## 阶段 7：Multi-Agent

- 状态：实现完成；Agent Registry、共享状态、严格 Handoff、固定 LangGraph、确定性 Verifier、
  简单问题快路径、节点 Trace 和同题对比 API 已加入。
- 图：`Supervisor -> Analysis -> Verifier` 固定执行且没有回边；成功和错误路径均恰好留下三个
  节点摘要，并继续受步数、调用数、Token、总时长和 recursion limit 约束。
- Verifier：测试覆盖错误金额、错误时间范围、错误方向、缺少计划 Tool 和缺少 Evidence；验证
  失败不返回未经验证的答案。
- 对比验收：同一 `stage5-v1` 30 题 mock 数据集分别强制运行 Single/Multi；两者均通过原 80%
  门槛，并达到 100% Tool 选择准确率和 100% Evidence 数值准确率；结果按 workflow 分别持久化。
- 数据库：迁移 `20260922_0005` 新增 Run/评测 workflow 和 `agent_step_traces`；全新升级、回退到
  阶段 6、再次升级均已通过。
- 延后项：按用户要求，本阶段不做真实 Ollama 与远程模型质量基线；API Key 配置后再用同一
  `--workflow compare` 数据集留档。
- 当前验证：后端 50 项测试与 Ruff 全部通过；阶段 6/7 针对性服务/API/失败路径及 30 题双
  工作流评测通过；Alembic upgrade/downgrade/upgrade 和 `check` 通过；前端 typecheck、
  Vitest（2 项）、build、lint 通过；临时 SQLite + Uvicorn 下导入、Semantic pending、
  Multi-Agent 三节点 Trace 和 Single/Multi 对比 HTTP 冒烟通过。

合同见 [`docs/data-contracts/stage7-multi-agent.md`](data-contracts/stage7-multi-agent.md)，API 见
[`docs/api/stage7-multi-agent.md`](api/stage7-multi-agent.md)。

## 阶段 8：Planner 与 Budget Agent

- 状态：实现完成；结构化任务图、预执行校验、拓扑波并行执行、Evidence 驱动的一次有界重规划、
  确定性 Budget Agent 和显式确认门禁已加入。
- 安全边界：拒绝未知 Agent/Tool、越权 Tool、非法参数、未知/自身/循环依赖；所有执行继续受
  步数、Tool/模型调用、Token、估算费用和总时长上限约束。
- Budget：只从 `get_spending_summary` Evidence 计算整数金额；草案、人工修改、确认、拒绝和同周期
  替换均留档。预算或结果分歧未经用户确认不会作为最终长期决策。
- 数据库：迁移 `20260923_0006` 新增计划 Trace、预算和确认表，以及 Run 估算费用字段。
- 验收覆盖：计划合法性/循环/权限、无依赖并行与依赖串行、一次重规划、预算确定性、确认门禁、
  Tool/费用上限和 HTTP API。

合同见 [`docs/data-contracts/stage8-planning.md`](data-contracts/stage8-planning.md)，API 见
[`docs/api/stage8-planning.md`](api/stage8-planning.md)。

## 阶段 9：Developer Console 与架构评测

- 状态：实现完成；本地 Developer 页面/API、Run 节点图、计划/Tool/Evidence/记忆 Trace、版本化
  评测和失败样本库已加入。
- 环境门禁：Developer API 仅在显式启用且 `APP_MODE=local|development|test` 时开放，其他环境
  返回 404；响应不暴露完整 prompt、reasoning、Tool 原始参数/结果或账单行。
- 架构对比：同一 `stage5-v1` 30 题依次运行 Single、Multi（无 Verifier）和 Multi+Verifier，
  量化任务完成率、准确率、Evidence 覆盖、幻觉率、路由、Handoff、P50/P95 延迟、Token 和费用。
- 数据库：迁移 `20260924_0007` 新增对比分组、扩展评测指标和版本化失败样本表。
- 延后项：按用户要求未运行真实 Ollama/远程模型质量基线；模型与 API Key 就绪后再用同一数据集
  补充留档。当前结果只代表确定性 mock。

合同见 [`docs/data-contracts/stage9-observability.md`](data-contracts/stage9-observability.md)，API 见
[`docs/api/stage9-observability.md`](api/stage9-observability.md)。

## 阶段 10：用户可控记忆

- 状态：实现完成；会话状态、长期偏好和知识分层，显式用户来源、冲突版本链、过期、软删除、
  查看/修改/删除页面和检索 hit/miss Trace 已加入。
- 写入边界：确认预算和用户选择保存的商户规则可进入长期记忆；模型自动分类、推测、待确认建议和
  未确认预算均不会写入。删除/过期记录被后续检索排除。
- 可解释性：Planner 仅注入最多 20 条有效 `user_confirmed` 记忆；访问 Trace 保存匹配 ID 和原因，
  查询原文只保留 SHA-256 指纹，并可在 Developer Console 查看。
- 数据库：迁移 `20260925_0008` 新增版本化记忆和访问 Trace 表。
- 验收覆盖：来源边界、商户规则/预算确认集成、已确认预算修改后的新版本、规则双向删除同步、
  冲突版本、默认/显式过期、删除后 miss、Owner 范围、CRUD API 和前端修改/删除交互。
- 当前验证：后端全量 61 项测试与 Ruff 通过；前端 typecheck、Vitest（4 项）、build 和 lint
  通过；Alembic 从空库升级到阶段 10、回退到阶段 7、再次升级及 `check` 均通过。临时 SQLite +
  Uvicorn 完成合成账单导入、Planner 预算草案、显式确认、长期记忆写入、次轮 memory hit 和
  Developer Run 聚合的真实 HTTP 冒烟。

合同见 [`docs/data-contracts/stage10-memory.md`](data-contracts/stage10-memory.md)，API 见
[`docs/api/stage10-memory.md`](api/stage10-memory.md)。

## 阶段 11：本地发行与安全

- 状态：实现完成；选择普通 Local Web，前后端只绑定回环地址，固定数据目录和最小权限容器发行
  已加入。
- 数据生命周期：Owner 范围 JSON ZIP 导出、一次性二次确认令牌、手工 SQLite 备份、摘要/完整性/
  Schema 校验恢复、恢复前安全快照和不可逆全量删除均已实现。
- 升级策略：未管理的本地 Schema 在兼容升级前自动创建 `pre_upgrade` 备份；Alembic 管理的旧库
  拒绝普通启动，并由 `python -m app.data_admin upgrade` 执行“先备份、后迁移”。
- 文件安全：CSV 文件签名、XLSX 路径穿越/条目数/解压大小/压缩比/加密及必要成员检查已加入；
  原始账单 TTL 删除严格限制在 uploads 目录，数据导出不包含原始账单或 `raw_path`。
- Agent 安全：账单内容封装为不可信 Tool 数据，模型只能看到原有只读 Tool；Single/Multi/Planner
  增加上下文字符限制，并继续受步数、调用、Token、费用、超时和 Tool 结果大小限制。
- UI/API：前端 `/settings` 显示数据目录与策略，并提供导出、备份、恢复、删除；后端
  `/api/v1/data/*` 只在本地模式开放，写操作还要求自定义本地确认 Header。
- 验收覆盖：备份—修改—恢复—删除演练、升级前备份、令牌单次使用、目录逃逸、伪装文件、恶意
  XLSX/ZIP Bomb、提示注入、上下文上限、Host 门禁和前端二次确认。
- 当前验证：后端全量 69 项测试与 Ruff 通过；前端 typecheck、Vitest（6 项）、lint 和生产构建
  通过；生产 npm 依赖审计为 0 个已知漏洞。Alembic 从空库升级、回退到阶段 7、再次升级和
  `check` 通过，`app.data_admin upgrade` 实测先生成无 WAL/SHM 依赖的保护快照再迁移。前后端
  发行镜像构建成功，并在临时数据目录完成健康检查、设置页、反向代理、Host 拒绝、安全响应头、
  只读根文件系统、capability 清空和回环端口绑定的运行态验收。

合同见 [`docs/data-contracts/stage11-security.md`](data-contracts/stage11-security.md)，API 见
[`docs/api/stage11-data-management.md`](api/stage11-data-management.md)，发行决策见
[`docs/adr/0001-local-web-release.md`](adr/0001-local-web-release.md)。

# Backend

阶段 0 提供 FastAPI 状态接口和 mock ModelProvider；阶段 1 提供无模型调用的微信 CSV Parser，
当前导入链路也支持微信 XLSX；阶段 3 提供确定性统计 Service 和 `/api/v1/stats/*` API。
阶段 4 提供后端内部的受控只读 Tool Registry、OwnerContext、超时执行、Trace 和
`evidence_id` 重放。阶段 5 提供 mock/local/remote ModelProvider、有界 LangGraph
Single-Agent、会话/运行 API、最小化模型 Trace 和 30 题评测。
阶段 6 提供规则优先的 Semantic Agent、低置信度人工确认和用户商户规则；阶段 7 提供固定
Supervisor/Analysis/Verifier 图、确定性验证、节点 Trace 和 Single/Multi 对比。
阶段 8 提供结构化 Planner、依赖波执行、有界重规划和确定性 Budget Agent；阶段 9 提供本地
Developer API、三架构评测和失败样本库；阶段 10 提供用户确认、版本化、可删除的记忆及访问 Trace。
阶段 11 提供固定本地数据目录、确认令牌、Owner 范围导出、SQLite 备份恢复、全量删除、上传容器
校验、提示注入隔离和模型上下文上限。

在 `backend` 目录运行：

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

阶段 4 Tool 合同见
[`docs/data-contracts/stage4-tools.md`](../docs/data-contracts/stage4-tools.md)，调用接口见
[`docs/api/stage4-tools.md`](../docs/api/stage4-tools.md)。由 Alembic 管理的数据库运行
`alembic upgrade head` 创建 `tool_traces` 表；未 stamp 的本地 MVP 数据库由启动时
`create_all` 自动补表。

阶段 5 合同见
[`docs/data-contracts/stage5-model-agent.md`](../docs/data-contracts/stage5-model-agent.md)，API
见 [`docs/api/stage5-agent.md`](../docs/api/stage5-agent.md)。启动后可调用：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"2026年1月总支出是多少？"}'
```

由 Alembic 管理的数据库运行 `alembic upgrade head`。本地 `create_all` 数据库启动时会安全地
补上阶段 5 所需的新表和 `tool_traces.run_id` 可空列。

阶段 6/7 合同分别见
[`docs/data-contracts/stage6-semantic.md`](../docs/data-contracts/stage6-semantic.md) 和
[`docs/data-contracts/stage7-multi-agent.md`](../docs/data-contracts/stage7-multi-agent.md)。示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"分析2026年1月每天的支出趋势","workflow":"multi"}'

python -m app.evals.runner --workflow compare \
  --fixture ../datasets/sanitized_samples/stage3_stats_fixture.csv
```

阶段 8 至 10 合同分别见：

- [`docs/data-contracts/stage8-planning.md`](../docs/data-contracts/stage8-planning.md)
- [`docs/data-contracts/stage9-observability.md`](../docs/data-contracts/stage9-observability.md)
- [`docs/data-contracts/stage10-memory.md`](../docs/data-contracts/stage10-memory.md)

三架构 mock 对比使用 `python -m app.evals.runner --workflow architecture`。本地启用
`DEVELOPER_ENABLED=true` 后可访问 `/api/v1/developer/*`；预算确认位于
`/api/v1/agent/confirmations`，用户记忆位于 `/api/v1/memories`。

阶段 11 合同见
[`docs/data-contracts/stage11-security.md`](../docs/data-contracts/stage11-security.md)，API 见
[`docs/api/stage11-data-management.md`](../docs/api/stage11-data-management.md)。Alembic 管理的本地
数据库应通过 `python -m app.data_admin upgrade` 升级，以保证旧版本在迁移前先生成保护备份。

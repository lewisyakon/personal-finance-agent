# Backend

阶段 0 提供 FastAPI 状态接口和 mock ModelProvider；阶段 1 提供无模型调用的微信 CSV Parser，
当前导入链路也支持微信 XLSX；阶段 3 提供确定性统计 Service 和 `/api/v1/stats/*` API。
阶段 4 提供后端内部的受控只读 Tool Registry、OwnerContext、超时执行、Trace 和
`evidence_id` 重放。阶段 5 提供 mock/local/remote ModelProvider、有界 LangGraph
Single-Agent、会话/运行 API、最小化模型 Trace 和 30 题评测。

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

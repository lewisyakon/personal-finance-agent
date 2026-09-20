# 阶段 4 Tool 接口

阶段 4 的 Tool 是 FastAPI 后端内部的受控函数接口，不是浏览器可直接调用的 HTTP API。
阶段 5 的 Agent 将从同一个 Registry 获取 JSON Schema，并通过 `ToolExecutor` 调用。

## Registry

`app.tools.registry.readonly_tool_registry` 提供：

- `definitions()`：返回固定、版本化的 Tool 定义；
- `model_tool_schemas()`：返回 Provider-neutral function schema；
- Schema 中不包含 `owner_id`。

## Runtime

调用形式：

```python
result = executor.execute(
    "get_spending_summary",
    {
        "from": "2026-01-01T00:00:00+08:00",
        "to": "2026-02-01T00:00:00+08:00",
    },
    OwnerContext(owner_id=trusted_owner_id),
)
```

`trusted_owner_id` 必须由服务端会话或本地工作区依赖注入，不能来自模型生成的参数。
结果和错误契约、分页限制、统计口径及 evidence 重放语义见
[`stage4-tools.md`](../data-contracts/stage4-tools.md)。

当前没有 `/api/v1/tools/*` 路由。这可以避免在尚未建立 Agent 会话、运行限额和取消协议前，
把内部 Tool 暴露成第二套统计 HTTP API。

## 数据迁移

执行 `alembic upgrade head` 会创建 `tool_traces` 表。首次本地启动仍由 `create_all` 自动补齐；
已经由 Alembic 管理的打包部署使用迁移升级。未 stamp 的本地 MVP 既有数据库继续使用启动时
`create_all` 补表，不应直接重复执行阶段 2 的初始迁移。
